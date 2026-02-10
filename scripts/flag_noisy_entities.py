#!/usr/bin/env python3
"""
Flag likely noisy/gibberish entities in the canonical registry.

This does NOT delete anything. It writes review files you can inspect:
  - CSV for spreadsheet review
  - JSONL for scripted workflows

Usage:
  python3 scripts/flag_noisy_entities.py
  python3 scripts/flag_noisy_entities.py --min-mentions 20
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_INPUT = ROOT / "web" / "public" / "data" / "entity_registry.json"
DEFAULT_CSV = ROOT / "data" / "quality" / "noisy_entity_candidates.csv"
DEFAULT_JSONL = ROOT / "data" / "quality" / "noisy_entity_candidates.jsonl"

OCR_NOISE_RE = re.compile(r"[»«^§|{}†‡¶•☉♀♈〈〉]")
BIB_RE = re.compile(r"\b(fol\.|lib\.|cap\.|timoth\b|regum\b)\b", re.I)
DATE_TEXT_RE = re.compile(
    r"\b(janeiro|fevereiro|marco|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|"
    r"january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.I,
)


def fold_special_latin(text: str) -> str:
    return (
        text.replace("Æ", "AE")
        .replace("æ", "ae")
        .replace("Œ", "OE")
        .replace("œ", "oe")
        .replace("ß", "ss")
        .replace("Ø", "O")
        .replace("ø", "o")
        .replace("Ð", "D")
        .replace("ð", "d")
        .replace("Þ", "Th")
        .replace("þ", "th")
    )


def normalize(text: str) -> str:
    text = fold_special_latin(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def classify_noise(name: str, total_mentions: int, min_mentions_for_non_latin: int) -> list[str]:
    reasons: list[str] = []
    raw = (name or "").strip()
    if not raw:
        return ["empty"]

    if OCR_NOISE_RE.search(raw):
        reasons.append("ocr_noise_char")

    folded = normalize(raw)
    if not folded:
        reasons.append("empty_after_normalize")

    if BIB_RE.search(raw):
        reasons.append("bibliographic_fragment")

    letters = sum(ch.isalpha() for ch in raw)
    digits = sum(ch.isdigit() for ch in raw)
    punct = sum((not ch.isalnum()) and (not ch.isspace()) for ch in raw)
    length = len(raw)
    has_latin = bool(re.search(r"[A-Za-zÀ-ÿ]", raw))

    if length <= 2 and total_mentions < 10:
        reasons.append("very_short_low_count")
    if re.match(r"^[0-9]{3,4}[a-z]?$", raw, re.I):
        reasons.append("year_or_page_token")
    if DATE_TEXT_RE.search(raw) and digits >= 1:
        reasons.append("date_phrase")
    if ("/" in raw or "\\" in raw) and total_mentions < 100:
        reasons.append("slash_noise")
    if re.search(r"[£€<>]", raw):
        reasons.append("symbol_noise")
    if re.search(r"^[_'\".()[\]{}]+|[_'\".()[\]{}]+$", raw):
        reasons.append("wrapped_punctuation")
    if letters == 0 and digits > 0:
        reasons.append("numeric_only")
    if letters == 0 and punct >= 2:
        reasons.append("punctuation_only")
    if (not has_latin) and total_mentions < min_mentions_for_non_latin:
        reasons.append("non_latin_low_count")
    if letters > 0 and punct / max(1, length) >= 0.35:
        reasons.append("high_punctuation_ratio")
    if digits >= 4 and digits / max(1, length) > 0.45:
        reasons.append("high_digit_ratio")
    if re.match(r"^[\W_].*[\W_]$", raw) and letters < 3:
        reasons.append("bounded_by_nonword")

    return reasons


def main() -> None:
    parser = argparse.ArgumentParser(description="Flag likely noisy entities for review")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Path to entity_registry.json")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Output CSV path")
    parser.add_argument("--jsonl", default=str(DEFAULT_JSONL), help="Output JSONL path")
    parser.add_argument(
        "--min-mentions",
        type=int,
        default=20,
        help="Minimum mentions before keeping non-Latin names",
    )
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        registry = json.load(f)

    entities = registry.get("entities", [])
    flagged = []
    for e in entities:
        reasons = classify_noise(
            e.get("canonical_name", ""),
            int(e.get("total_mentions", 0)),
            min_mentions_for_non_latin=args.min_mentions,
        )
        if not reasons:
            continue
        flagged.append(
            {
                "id": e.get("id"),
                "slug": e.get("slug"),
                "canonical_name": e.get("canonical_name"),
                "category": e.get("category"),
                "book_count": int(e.get("book_count", 0)),
                "total_mentions": int(e.get("total_mentions", 0)),
                "reasons": reasons,
                "books": e.get("books", [])[:6],
            }
        )

    flagged.sort(key=lambda x: (len(x["reasons"]), x["total_mentions"], x["canonical_name"].lower()), reverse=True)

    csv_path = Path(args.csv)
    jsonl_path = Path(args.jsonl)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "slug",
                "canonical_name",
                "category",
                "book_count",
                "total_mentions",
                "reason_count",
                "reasons",
                "books",
            ],
        )
        writer.writeheader()
        for row in flagged:
            writer.writerow(
                {
                    "id": row["id"],
                    "slug": row["slug"],
                    "canonical_name": row["canonical_name"],
                    "category": row["category"],
                    "book_count": row["book_count"],
                    "total_mentions": row["total_mentions"],
                    "reason_count": len(row["reasons"]),
                    "reasons": ";".join(row["reasons"]),
                    "books": ";".join(row["books"]),
                }
            )

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for row in flagged:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Scanned {len(entities):,} entities")
    print(f"Flagged {len(flagged):,} candidates")
    print(f"CSV:   {csv_path}")
    print(f"JSONL: {jsonl_path}")


if __name__ == "__main__":
    main()
