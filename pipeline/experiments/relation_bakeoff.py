#!/usr/bin/env python3
"""Compare inexpensive LLMs on historical typed entity resolution.

The experiment uses the project's two expert-labeled datasets:

* membership_decisions.jsonl: does a candidate belong in an entity cluster?
* synonym_chain_examples.jsonl: what relation does a passage actually assert?

Predictions and request-level usage are checkpointed under var/experiments so a
run can be resumed without repeating paid calls.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field


REPOSITORY = Path(__file__).resolve().parents[2]
MEMBERSHIP_PATH = REPOSITORY / "data" / "training" / "membership_decisions.jsonl"
SYNONYM_PATH = REPOSITORY / "data" / "training" / "synonym_chain_examples.jsonl"
DEFAULT_OUTPUT_ROOT = REPOSITORY / "var" / "experiments"

Relationship = Literal[
    "orthographic_variant",
    "cross_linguistic",
    "same_referent",
    "descriptive_phrase",
    "true_synonym",
    "subtype_relation",
    "conceptual_overlap",
    "contested_identity",
    "ingredient_cooccurrence",
    "authority_cooccurrence",
    "ocr_noise",
    "generic_term",
    "unrelated",
]


class Prediction(BaseModel):
    id: str
    linked: bool
    relationship: Relationship
    confidence: Literal["high", "medium", "low"]
    reason: str = Field(description="A concise evidence-based reason.", max_length=180)


class PredictionBatch(BaseModel):
    results: list[Prediction]


@dataclass(frozen=True)
class ModelConfig:
    provider: Literal["openai", "gemini"]
    model: str
    input_per_million: float
    output_per_million: float
    reasoning: str


MODELS: dict[str, ModelConfig] = {
    "gpt-5-nano-2025-08-07": ModelConfig(
        provider="openai",
        model="gpt-5-nano-2025-08-07",
        input_per_million=0.05,
        output_per_million=0.40,
        reasoning="minimal",
    ),
    "gpt-5.4-nano": ModelConfig(
        provider="openai",
        model="gpt-5.4-nano",
        input_per_million=0.20,
        output_per_million=1.25,
        reasoning="none",
    ),
    "gemini-3.1-flash-lite": ModelConfig(
        provider="gemini",
        model="gemini-3.1-flash-lite",
        input_per_million=0.25,
        output_per_million=1.50,
        reasoning="minimal",
    ),
}

SYSTEM_PROMPT = """You resolve entities in multilingual historical scientific and medical texts.
Judge the evidence presented, including context and wording. Do not merge things merely because
they are associated or similar. Historical authors may explicitly equate things that modern
scholarship distinguishes; classify that as contested_identity when the evidence supports it.
Return exactly one prediction for every supplied id as structured JSON."""

LABEL_GUIDE = """Relationship labels:
- orthographic_variant: spelling, OCR, inflectional, or closely lexical variant of the same name
- cross_linguistic: translation or vernacular name in another language for the same referent
- same_referent: substantially different names that denote the same entity
- descriptive_phrase: a descriptive phrase used to refer to the entry
- true_synonym: the passage explicitly presents two terms as equivalent
- subtype_relation: the candidate is a kind, variety, or narrower instance of the entry
- conceptual_overlap: historically related concepts that are not identical
- contested_identity: the source or historical tradition equates entities whose identity is disputed
- ingredient_cooccurrence: substances only occur together in a recipe or list
- authority_cooccurrence: people or authorities are merely mentioned together
- ocr_noise: the candidate is an OCR artifact
- generic_term: the candidate is too generic to function as this entity
- unrelated: none of the above relationships is supported

Set linked=true only for the first eight relationship labels, through contested_identity.
Set linked=false for cooccurrence, OCR noise, generic terms, and unrelated items."""

MEMBERSHIP_TASK = """Task: decide whether each candidate belongs in the proposed concordance entry.
A translation, variant, same referent, descriptive historical name, or documented subtype belongs.
Association alone does not. Use the most precise relationship label."""

SYNONYM_TASK = """Task: classify what relationship the supplied passage supports between the known
entry and the found term. Distinguish explicit equivalence from recipes, authority lists, OCR noise,
subtypes, and historically contested identifications."""

MEMBERSHIP_RELATION_MAP = {
    "variant": "orthographic_variant",
    "translation": "cross_linguistic",
    "phrase": "descriptive_phrase",
    "subtype": "subtype_relation",
    "mismatch": "unrelated",
}

NEGATIVE_RELATIONSHIPS = {
    "ingredient_cooccurrence",
    "authority_cooccurrence",
    "ocr_noise",
    "generic_term",
    "unrelated",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def stratified_sample(items: list[dict], size: int, seed: int) -> list[dict]:
    """Sample across gold patterns while retaining at least one rare example."""
    if size >= len(items):
        return items
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        groups[item["gold_pattern"]].append(item)
    rng = random.Random(seed)
    for group in groups.values():
        rng.shuffle(group)

    allocation = {pattern: 1 for pattern in groups}
    remaining = size - len(allocation)
    if remaining < 0:
        selected_patterns = sorted(groups, key=lambda key: len(groups[key]), reverse=True)[:size]
        allocation = {pattern: 1 for pattern in selected_patterns}
        remaining = 0

    while remaining:
        candidates = [
            pattern
            for pattern, group in groups.items()
            if allocation.get(pattern, 0) < len(group)
        ]
        if not candidates:
            break
        pattern = max(
            candidates,
            key=lambda key: len(groups[key]) / (allocation.get(key, 0) + 1),
        )
        allocation[pattern] = allocation.get(pattern, 0) + 1
        remaining -= 1

    sampled = [
        item
        for pattern, count in allocation.items()
        for item in groups[pattern][:count]
    ]
    return sorted(sampled, key=lambda item: item["id"])


def load_examples(
    limit_per_task: int | None = None,
    sample_size: int | None = None,
    seed: int = 20260716,
) -> list[dict]:
    examples: list[dict] = []
    membership = read_jsonl(MEMBERSHIP_PATH)
    synonyms = read_jsonl(SYNONYM_PATH)
    if limit_per_task:
        membership = membership[:limit_per_task]
        synonyms = synonyms[:limit_per_task]

    for index, row in enumerate(membership):
        examples.append(
            {
                "id": f"membership:{index:04d}",
                "task": "membership",
                "prompt_item": {
                    "id": f"membership:{index:04d}",
                    "proposed_entry": row["anchor_text"],
                    "candidate": row["candidate_text"],
                    "source": row.get("member_source", ""),
                },
                "gold_linked": bool(row["label"]),
                "gold_relationship": MEMBERSHIP_RELATION_MAP[row["pattern"]],
                "gold_pattern": row["pattern"],
                "expert_reason": row.get("reason", ""),
            }
        )

    for index, row in enumerate(synonyms):
        identifier = f"synonym:{index:04d}"
        examples.append(
            {
                "id": identifier,
                "task": "synonym",
                "prompt_item": {
                    "id": identifier,
                    "known_entry": {
                        "name": row["source_cluster_name"],
                        "modern_name": row.get("source_modern_name", ""),
                        "category": row["source_category"],
                        "attested_form": row.get("source_member", ""),
                    },
                    "found_term": row["found_name"],
                    "found_category": row.get("found_category", ""),
                    "passage": row["excerpt"],
                },
                "gold_linked": bool(row["is_genuine_link"]),
                "gold_relationship": row["expert_label"],
                "gold_pattern": row["expert_label"],
                "expert_reason": row.get("expert_reasoning", ""),
            }
        )
    if not sample_size or sample_size >= len(examples):
        return examples

    membership_examples = [example for example in examples if example["task"] == "membership"]
    synonym_examples = [example for example in examples if example["task"] == "synonym"]
    membership_size = min(len(membership_examples), round(sample_size * 0.70))
    synonym_size = min(len(synonym_examples), sample_size - membership_size)
    if membership_size + synonym_size < sample_size:
        membership_size = min(
            len(membership_examples), sample_size - synonym_size
        )
    return sorted(
        stratified_sample(membership_examples, membership_size, seed)
        + stratified_sample(synonym_examples, synonym_size, seed + 1),
        key=lambda example: example["id"],
    )


def chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def build_prompt(task: str, examples: list[dict]) -> str:
    task_prompt = MEMBERSHIP_TASK if task == "membership" else SYNONYM_TASK
    items = [example["prompt_item"] for example in examples]
    return f"{task_prompt}\n\n{LABEL_GUIDE}\n\nITEMS:\n{json.dumps(items, ensure_ascii=False)}"


def cost(config: ModelConfig, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * config.input_per_million
        + output_tokens * config.output_per_million
    ) / 1_000_000


def call_openai(config: ModelConfig, prompt: str, batch_size: int) -> tuple[PredictionBatch, dict]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=90.0)
    response = client.responses.parse(
        model=config.model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        text_format=PredictionBatch,
        reasoning={"effort": config.reasoning},
        max_output_tokens=max(
            24000 if config.model.startswith("gpt-") else 4000,
            batch_size * 240,
        ),
        store=False,
    )
    if response.output_parsed is None:
        raise RuntimeError(f"{config.model} returned no parsed output: {response.output_text[:500]}")
    usage = response.usage
    details = getattr(usage, "output_tokens_details", None)
    return response.output_parsed, {
        "input_tokens": int(usage.input_tokens),
        "output_tokens": int(usage.output_tokens),
        "reasoning_tokens": int(getattr(details, "reasoning_tokens", 0) or 0),
        "cached_input_tokens": int(
            getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
        ),
    }


def call_gemini(config: ModelConfig, prompt: str, batch_size: int) -> tuple[PredictionBatch, dict]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=config.model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=PredictionBatch,
            temperature=0,
            max_output_tokens=max(4000, batch_size * 240),
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        ),
    )
    parsed = PredictionBatch.model_validate_json(response.text)
    usage = response.usage_metadata
    candidate_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    thought_tokens = int(getattr(usage, "thoughts_token_count", 0) or 0)
    return parsed, {
        "input_tokens": int(getattr(usage, "prompt_token_count", 0) or 0),
        "output_tokens": candidate_tokens + thought_tokens,
        "visible_output_tokens": candidate_tokens,
        "reasoning_tokens": thought_tokens,
        "cached_input_tokens": int(getattr(usage, "cached_content_token_count", 0) or 0),
    }


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def completed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {row["id"] for row in read_jsonl(path)}


def usage_total(path: Path) -> float:
    if not path.exists():
        return 0.0
    return sum(float(row.get("cost_usd", 0)) for row in read_jsonl(path))


def validate_predictions(batch: list[dict], parsed: PredictionBatch) -> dict[str, Prediction]:
    expected = {example["id"] for example in batch}
    by_id = {prediction.id: prediction for prediction in parsed.results}
    missing = expected - by_id.keys()
    unexpected = by_id.keys() - expected
    if missing or unexpected:
        raise ValueError(
            f"prediction ids do not match batch; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}, duplicates={len(parsed.results) - len(by_id)}"
        )
    return by_id


def run_model(
    config: ModelConfig,
    examples: list[dict],
    output_dir: Path,
    batch_size: int,
    max_total_cost: float,
) -> dict:
    predictions_path = output_dir / f"{config.model}.predictions.jsonl"
    requests_path = output_dir / f"{config.model}.requests.jsonl"
    done = completed_ids(predictions_path)
    remaining = [example for example in examples if example["id"] not in done]
    current_cost = sum(
        usage_total(output_dir / f"{model.model}.requests.jsonl") for model in MODELS.values()
    )
    print(
        f"\n{config.model}: {len(done)} complete, {len(remaining)} remaining, "
        f"run cost so far ${current_cost:.4f}",
        flush=True,
    )

    grouped: dict[str, list[dict]] = defaultdict(list)
    for example in remaining:
        grouped[example["task"]].append(example)
    model_batches = [
        batch
        for task in ("membership", "synonym")
        for batch in chunks(grouped[task], batch_size)
    ]

    for batch_number, batch in enumerate(model_batches, start=1):
        current_cost = sum(
            usage_total(output_dir / f"{model.model}.requests.jsonl")
            for model in MODELS.values()
        )
        if current_cost >= max_total_cost:
            raise RuntimeError(
                f"cost ceiling reached before request: ${current_cost:.4f} >= ${max_total_cost:.2f}"
            )

        prompt = build_prompt(batch[0]["task"], batch)
        started = time.perf_counter()
        try:
            if config.provider == "openai":
                parsed, usage = call_openai(config, prompt, len(batch))
            else:
                parsed, usage = call_gemini(config, prompt, len(batch))
            latency = time.perf_counter() - started
            by_id = validate_predictions(batch, parsed)
            request_cost = cost(config, usage["input_tokens"], usage["output_tokens"])
            append_jsonl(
                requests_path,
                {
                    "timestamp": utc_now(),
                    "model": config.model,
                    "task": batch[0]["task"],
                    "batch_size": len(batch),
                    "latency_seconds": round(latency, 4),
                    **usage,
                    "cost_usd": request_cost,
                    "status": "ok",
                },
            )
            for example in batch:
                prediction = by_id[example["id"]]
                append_jsonl(
                    predictions_path,
                    {
                        "timestamp": utc_now(),
                        "model": config.model,
                        "id": example["id"],
                        "task": example["task"],
                        "gold_linked": example["gold_linked"],
                        "gold_relationship": example["gold_relationship"],
                        "gold_pattern": example["gold_pattern"],
                        "expert_reason": example["expert_reason"],
                        "prediction": prediction.model_dump(),
                    },
                )
            print(
                f"  [{batch_number:02d}/{len(model_batches):02d}] {batch[0]['task']} "
                f"{len(batch)} items, {latency:.1f}s, ${request_cost:.4f}",
                flush=True,
            )
        except Exception as exc:
            latency = time.perf_counter() - started
            append_jsonl(
                requests_path,
                {
                    "timestamp": utc_now(),
                    "model": config.model,
                    "task": batch[0]["task"],
                    "batch_size": len(batch),
                    "latency_seconds": round(latency, 4),
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            print(f"  ERROR after {latency:.1f}s: {type(exc).__name__}: {exc}", flush=True)
            raise
    return {"model": config.model, "completed": len(completed_ids(predictions_path))}


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def binary_metrics(gold: list[bool], predicted: list[bool]) -> dict[str, float | int]:
    tp = sum(g and p for g, p in zip(gold, predicted))
    tn = sum(not g and not p for g, p in zip(gold, predicted))
    fp = sum(not g and p for g, p in zip(gold, predicted))
    fn = sum(g and not p for g, p in zip(gold, predicted))
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    specificity = safe_div(tn, tn + fp)
    return {
        "n": len(gold),
        "accuracy": safe_div(tp + tn, len(gold)),
        "balanced_accuracy": (recall + specificity) / 2,
        "precision": precision,
        "recall": recall,
        "f1": safe_div(2 * precision * recall, precision + recall),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def evaluate_model(config: ModelConfig, output_dir: Path) -> dict:
    predictions_path = output_dir / f"{config.model}.predictions.jsonl"
    requests_path = output_dir / f"{config.model}.requests.jsonl"
    rows = read_jsonl(predictions_path) if predictions_path.exists() else []
    requests = read_jsonl(requests_path) if requests_path.exists() else []
    by_task = defaultdict(list)
    for row in rows:
        by_task[row["task"]].append(row)

    result: dict = {"model": config.model, "provider": config.provider}
    for task in ("membership", "synonym"):
        task_rows = by_task[task]
        gold = [bool(row["gold_linked"]) for row in task_rows]
        predicted = [bool(row["prediction"]["linked"]) for row in task_rows]
        metrics = binary_metrics(gold, predicted) if task_rows else binary_metrics([], [])
        metrics["typed_accuracy"] = safe_div(
            sum(
                row["gold_relationship"] == row["prediction"]["relationship"]
                for row in task_rows
            ),
            len(task_rows),
        )
        metrics["logical_consistency"] = safe_div(
            sum(
                bool(row["prediction"]["linked"])
                == (row["prediction"]["relationship"] not in NEGATIVE_RELATIONSHIPS)
                for row in task_rows
            ),
            len(task_rows),
        )
        per_pattern: dict[str, dict] = {}
        for pattern in sorted({row["gold_pattern"] for row in task_rows}):
            subset = [row for row in task_rows if row["gold_pattern"] == pattern]
            per_pattern[pattern] = {
                "n": len(subset),
                "link_accuracy": safe_div(
                    sum(
                        bool(row["gold_linked"]) == bool(row["prediction"]["linked"])
                        for row in subset
                    ),
                    len(subset),
                ),
                "typed_accuracy": safe_div(
                    sum(
                        row["gold_relationship"] == row["prediction"]["relationship"]
                        for row in subset
                    ),
                    len(subset),
                ),
            }
        metrics["by_pattern"] = per_pattern
        result[task] = metrics

    successful_requests = [row for row in requests if row.get("status") == "ok"]
    result["usage"] = {
        "requests": len(successful_requests),
        "errors": sum(row.get("status") == "error" for row in requests),
        "input_tokens": sum(int(row.get("input_tokens", 0)) for row in successful_requests),
        "output_tokens": sum(int(row.get("output_tokens", 0)) for row in successful_requests),
        "reasoning_tokens": sum(
            int(row.get("reasoning_tokens", 0)) for row in successful_requests
        ),
        "cost_usd": sum(float(row.get("cost_usd", 0)) for row in successful_requests),
        "total_latency_seconds": sum(
            float(row.get("latency_seconds", 0)) for row in successful_requests
        ),
        "median_request_latency_seconds": (
            statistics.median(
                float(row.get("latency_seconds", 0)) for row in successful_requests
            )
            if successful_requests
            else 0
        ),
    }
    return result


def format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_report(metrics: list[dict], output_dir: Path, expected_examples: int) -> None:
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    complete = [
        row
        for row in metrics
        if row["membership"]["n"] + row["synonym"]["n"] == expected_examples
    ]
    ranked = sorted(
        complete,
        key=lambda row: row["membership"]["balanced_accuracy"],
        reverse=True,
    )
    lines = [
        "# Historical relation-classification bake-off",
        "",
        f"Generated: {utc_now()}",
        f"Expert-labeled examples per complete model: {expected_examples}",
        "",
        "| Model | Membership balanced accuracy | Membership F1 | Synonym link accuracy | Synonym typed accuracy | Cost |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in ranked:
        lines.append(
            f"| `{row['model']}` | {format_pct(row['membership']['balanced_accuracy'])} "
            f"| {format_pct(row['membership']['f1'])} "
            f"| {format_pct(row['synonym']['accuracy'])} "
            f"| {format_pct(row['synonym']['typed_accuracy'])} "
            f"| ${row['usage']['cost_usd']:.4f} |"
        )
    lines.extend(
        [
            "",
            "Ranking uses membership balanced accuracy. The synonym sample is reported but is too small to rank models.",
            "Full per-pattern metrics and token usage are in `metrics.json`.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=[*MODELS, "all"],
        default=["all"],
    )
    parser.add_argument("--run-id", default=datetime.now().strftime("relation-bakeoff-%Y%m%d"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--limit-per-task", type=int)
    parser.add_argument("--sample-size", type=int)
    parser.add_argument("--seed", type=int, default=20260716)
    parser.add_argument(
        "--match-completed-model",
        choices=list(MODELS),
        help="Evaluate only ids already completed by this model in the same run.",
    )
    parser.add_argument("--max-cost", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    load_dotenv(REPOSITORY / ".env.local")
    model_names = list(MODELS) if "all" in arguments.models else arguments.models
    output_dir = arguments.output_root / arguments.run_id
    examples = load_examples(
        limit_per_task=arguments.limit_per_task,
        sample_size=arguments.sample_size,
        seed=arguments.seed,
    )
    if arguments.match_completed_model:
        reference_path = (
            output_dir
            / f"{arguments.match_completed_model}.predictions.jsonl"
        )
        reference_ids = completed_ids(reference_path)
        if not reference_ids:
            raise SystemExit(f"No completed predictions found at {reference_path}")
        examples = [example for example in examples if example["id"] in reference_ids]
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": utc_now(),
        "models": [asdict(MODELS[name]) for name in model_names],
        "membership_source": str(MEMBERSHIP_PATH.relative_to(REPOSITORY)),
        "synonym_source": str(SYNONYM_PATH.relative_to(REPOSITORY)),
        "example_count": len(examples),
        "sample_size": arguments.sample_size,
        "seed": arguments.seed,
        "match_completed_model": arguments.match_completed_model,
        "batch_size": arguments.batch_size,
        "max_cost_usd": arguments.max_cost,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"Run {arguments.run_id}: {len(examples)} examples, {len(model_names)} models, "
        f"cost ceiling ${arguments.max_cost:.2f}",
        flush=True,
    )
    print(
        "Tasks: "
        + ", ".join(
            f"{task}={sum(example['task'] == task for example in examples)}"
            for task in ("membership", "synonym")
        ),
        flush=True,
    )
    if arguments.dry_run:
        sample = [example for example in examples if example["task"] == "membership"][:2]
        print(build_prompt("membership", sample))
        return

    if any(MODELS[name].provider == "openai" for name in model_names):
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is required")
    if any(MODELS[name].provider == "gemini" for name in model_names):
        if not os.environ.get("GEMINI_API_KEY"):
            raise SystemExit("GEMINI_API_KEY is required")

    for name in model_names:
        run_model(
            MODELS[name],
            examples,
            output_dir,
            arguments.batch_size,
            arguments.max_cost,
        )
        write_report(
            [evaluate_model(MODELS[model], output_dir) for model in model_names],
            output_dir,
            len(examples),
        )

    metrics = [evaluate_model(MODELS[name], output_dir) for name in model_names]
    write_report(metrics, output_dir, len(examples))
    print(f"\nResults: {output_dir / 'report.md'}", flush=True)
    print(
        f"Total measured cost: ${sum(row['usage']['cost_usd'] for row in metrics):.4f}",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted; checkpoints are safe to resume.", file=sys.stderr)
        raise SystemExit(130)
