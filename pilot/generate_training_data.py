#!/usr/bin/env python3
"""
Generate training data for fine-tuning lightweight LLMs on entity extraction.
Target models: Qwen3-0.6B (fastest), Qwen3-1.7B, or SmolLM3-3B

Uses Gemini 2.5 Flash Lite as teacher model to label chunks.

Usage:
    python generate_training_data.py --input books/polyanthea_medicinal.txt --samples 500
"""

import argparse
import json
import os
import random
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# Load environment variables from .env.local
load_dotenv(".env.local")

# --- Configuration ---

CHUNK_SIZE = 2000  # Smaller chunks for training examples
CHUNK_OVERLAP = 100

TEACHER_PROMPT = """You are an expert in early modern European medicine, natural philosophy, and pharmacy.
Extract ALL named entities from this passage from an early modern text (16th-18th century).

Categories:
- PERSON: physicians, philosophers, ancient authorities, translators, rulers
- SUBSTANCE: drugs, plants, minerals, animal products, chemical preparations
- CONCEPT: diseases, medical theories, procedures, anatomical terms

For each entity provide:
- name: exactly as it appears (preserve original spelling)
- category: PERSON, SUBSTANCE, or CONCEPT
- context: brief description (max 8 words)

Return ONLY a JSON array. Example:
[{"name": "Galeno", "category": "PERSON", "context": "ancient medical authority"},
 {"name": "ruybarbo", "category": "SUBSTANCE", "context": "purgative drug from China"}]

PASSAGE:
"""


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks for training examples."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)  # Normalize spaces

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunk = text[start:].strip()
            if len(chunk) > 200:  # Only keep substantial chunks
                chunks.append(chunk)
            break

        # Try to break at paragraph
        break_point = text.rfind('\n\n', start + chunk_size // 2, end)
        if break_point == -1:
            break_point = text.rfind('. ', start + chunk_size // 2, end)
        if break_point == -1:
            break_point = end
        else:
            break_point += 2

        chunk = text[start:break_point].strip()
        if len(chunk) > 200:
            chunks.append(chunk)
        start = break_point - CHUNK_OVERLAP

    return chunks


class GeminiTeacher:
    """Use Gemini 2.5 Flash Lite as teacher model."""

    def __init__(self, model="gemini-2.5-flash-lite"):
        self.model = model
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or .env.local")
        self.client = genai.Client(api_key=api_key)

    def label(self, text: str) -> list[dict] | None:
        """Get entity labels from teacher model."""
        prompt = TEACHER_PROMPT + text + "\n\nJSON:"

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 1500,
                }
            )

            text_out = response.text

            # Parse JSON from response
            match = re.search(r'\[.*\]', text_out, re.DOTALL)
            if match:
                entities = json.loads(match.group())
                # Validate structure
                valid = []
                for e in entities:
                    if all(k in e for k in ["name", "category", "context"]):
                        if e["category"] in ["PERSON", "SUBSTANCE", "CONCEPT"]:
                            valid.append(e)
                return valid if valid else None
        except Exception as e:
            print(f"  Warning: {e}")
        return None


def format_for_training(passage: str, entities: list[dict]) -> dict:
    """
    Format a single example for fine-tuning.
    Uses chat format with system/user/assistant messages.
    """
    system_msg = """You extract named entities from early modern European texts (1500-1800).
Return a JSON array with name, category (PERSON/SUBSTANCE/CONCEPT), and brief context."""

    user_msg = f"""Extract all named entities from this passage:

{passage}"""

    assistant_msg = json.dumps(entities, ensure_ascii=False)

    return {
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg}
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Generate training data for entity extraction")
    parser.add_argument("--input", required=True, help="Input text file(s)", nargs="+")
    parser.add_argument("--output", default="pilot/entity_training_data.jsonl", help="Output JSONL file")
    parser.add_argument("--samples", type=int, default=500, help="Number of training examples to generate")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model to use as teacher")
    args = parser.parse_args()

    # Collect all chunks from all input files
    all_chunks = []
    for input_path in args.input:
        print(f"Loading {input_path}...")
        text = Path(input_path).read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_text(text)
        all_chunks.extend(chunks)
        print(f"  {len(chunks)} chunks")

    print(f"\nTotal chunks available: {len(all_chunks)}")

    # Sample chunks for training
    if len(all_chunks) > args.samples:
        selected_chunks = random.sample(all_chunks, args.samples)
    else:
        selected_chunks = all_chunks

    print(f"Selected {len(selected_chunks)} chunks for labeling\n")

    # Initialize teacher
    teacher = GeminiTeacher(args.model)
    print(f"Using teacher: {args.model}\n")

    # Generate training examples
    training_data = []
    failed = 0

    for i, chunk in enumerate(selected_chunks):
        print(f"Labeling {i+1}/{len(selected_chunks)}...", end=" ", flush=True)

        entities = teacher.label(chunk)

        if entities and len(entities) >= 2:  # At least 2 entities for useful example
            example = format_for_training(chunk, entities)
            training_data.append(example)
            print(f"✓ {len(entities)} entities")
        else:
            failed += 1
            print("✗ skipped")

        # Rate limiting - Gemini has generous limits but be safe
        time.sleep(0.3)

    # Save training data
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for example in training_data:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    print(f"\n{'='*50}")
    print(f"Generated {len(training_data)} training examples")
    print(f"Failed/skipped: {failed}")
    print(f"Saved to: {output_path}")

    # Also save a sample for review
    sample_path = output_path.with_suffix(".sample.json")
    with open(sample_path, "w", encoding="utf-8") as f:
        json.dump(training_data[:10], f, ensure_ascii=False, indent=2)
    print(f"Sample (first 10) saved to: {sample_path}")


if __name__ == "__main__":
    main()
