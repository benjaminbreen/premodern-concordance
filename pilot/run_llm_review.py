#!/usr/bin/env python3
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
import pandas as pd

# Load .env.local from pilot directory
load_dotenv(Path(__file__).parent / ".env.local")


def build_prompt(row):
    return (
        "You are evaluating whether two terms from historical scientific texts refer to the same entity.\n\n"
        f"Term A: \"{row['term_a']}\" (Language: {row['lang_a']}, Source: {row['source_a']})\n"
        f"Term B: \"{row['term_b']}\" (Language: {row['lang_b']}, Source: {row['source_b']})\n\n"
        "Do these terms refer to the same entity (species, substance, preparation)?\n\n"
        "Respond with:\n"
        "1. Decision: MATCH / NO MATCH / UNCERTAIN\n"
        "2. Confidence: HIGH / MEDIUM / LOW\n"
        "3. Reasoning: short explanation\n"
        "4. Link type (if MATCH): same_referent / orthographic_variant / conceptual_overlap / derivation"
    )


def main():
    parser = argparse.ArgumentParser(description="LLM review for uncertain embedding pairs.")
    parser.add_argument("--results", default="pilot/embedding_results.csv", help="embedding results CSV")
    parser.add_argument("--low", type=float, default=0.4, help="lower similarity bound")
    parser.add_argument("--high", type=float, default=0.7, help="upper similarity bound")
    parser.add_argument("--out", default="pilot/llm_review.csv", help="output CSV")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model")
    parser.add_argument("--dry-run", action="store_true", help="print prompts without calling API")
    args = parser.parse_args()

    df = pd.read_csv(args.results)
    uncertain = df[(df["similarity"] >= args.low) & (df["similarity"] <= args.high)].copy()

    if args.dry_run:
        for _, row in uncertain.iterrows():
            print("---")
            print(build_prompt(row))
        return

    try:
        from google import genai
    except Exception as exc:
        raise SystemExit("google-genai package not installed. pip install google-genai") from exc

    # The SDK picks up GEMINI_API_KEY automatically; GOOGLE_API_KEY also works for many setups.
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key) if api_key else genai.Client()

    outputs = []
    for _, row in uncertain.iterrows():
        prompt = build_prompt(row)
        resp = client.models.generate_content(
            model=args.model,
            contents=prompt,
        )
        text = getattr(resp, "text", "") or ""
        outputs.append({
            **row.to_dict(),
            "llm_response": text,
        })

    out_df = pd.DataFrame(outputs)
    out_df.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
