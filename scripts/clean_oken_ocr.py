#!/usr/bin/env python3
"""
Clean OCR text of Oken's Lehrbuch der Naturphilosophie (1809).

Fixes common issues from Google Books Fraktur OCR:
1. Strips "Digitized by Google" watermark lines
2. Converts HTML entities (&gt; &lt; &amp; etc.)
3. Removes front matter (title pages, TOC)
4. Strips page numbers, scanner artifacts, blank-line clusters
5. Fixes common Fraktur long-s OCR errors (f→s, f→ß)
6. Rejoins hyphenated words split across lines
7. Collapses excessive whitespace

Usage:
    python3 scripts/clean_oken_ocr.py
"""

import re
import html
from pathlib import Path

INPUT = Path("books/lehrbuchdernatu04okengoog_djvu.txt")
OUTPUT = Path("books/lehrbuch_naturphilosophie_oken_1809.txt")

# ─── Fraktur long-s corrections ─────────────────────────────────────────────
# In Fraktur, long-s (ſ) looks like f. OCR consistently misreads it.
# These are common German words/endings where f should be s/ß.
# Only correct patterns that are unambiguous.

# Word-level replacements (case-insensitive matching, preserve case)
WORD_FIXES = {
    # Very common function words
    "dafe": "daß",
    "dafs": "daß",
    "Dafe": "Daß",
    "Dafs": "Daß",
    "mufs": "muß",
    "Mufs": "Muß",
    "laefst": "läßt",
    "lafst": "laßt",
    "läfst": "läßt",
    "lässt": "läßt",
    "grofse": "große",
    "Grofse": "Große",
    "grofsen": "großen",
    "Grofsen": "Großen",
    "grofsem": "großem",
    "grofser": "großer",
    "grofscs": "großes",
    "grofses": "großes",
    "grofs": "groß",
    "Grofs": "Groß",
    "gewifs": "gewiß",
    "Gewifs": "Gewiß",
    "gcwifs": "gewiß",
    "blofs": "bloß",
    "Blofs": "Bloß",
    "weifs": "weiß",
    "Weifs": "Weiß",
    "heifst": "heißt",
    "Heifst": "Heißt",
    "heifsen": "heißen",
    "Heifsen": "Heißen",
    "äufsere": "äußere",
    "Äufsere": "Äußere",
    "äufseren": "äußeren",
    "äufserer": "äußerer",
    "äufserlich": "äußerlich",
    "aufser": "außer",
    "Aufser": "Außer",
    "aufserdem": "außerdem",
    "Aufserdem": "Außerdem",
    "aufserhalb": "außerhalb",
    "Aufserhalb": "Außerhalb",
    "ausser": "außer",
    "Ausser": "Außer",
    "gemäfs": "gemäß",
    "Gemäfs": "Gemäß",
    "gleichfalls": "gleichfalls",  # keep — this is correct
    "Gleichfalls": "Gleichfalls",
    "fchon": "schon",
    "Fchon": "Schon",
    "fchlecht": "schlecht",
    "fchlechte": "schlechte",
    "fchlechten": "schlechten",
    "fchlechter": "schlechter",
    "fchlechtes": "schlechtes",
    "Gcfchlechts": "Geschlechts",
    "Gefchlechts": "Geschlechts",
    "Gcfchlecht": "Geschlecht",
    "Gefchlecht": "Geschlecht",
    "Geschlccbt": "Geschlecht",

    # Common scientific terms
    "Sanerstoff": "Sauerstoff",
    "Sanersroff": "Sauerstoff",
    "Saucrftoff": "Sauerstoff",
    "Sauerstoffgas": "Sauerstoffgas",
    "Sanerstoffgas": "Sauerstoffgas",
    "Wafser": "Wasser",
    "Waffer": "Wasser",
    "Waffers": "Wassers",
    "Waffers": "Wassers",
    "Procefs": "Proceß",
    "Procefse": "Processe",
    "Proceffe": "Processe",
    "procefs": "Proceß",
    "Kohlensänre": "Kohlensäure",
    "Kohlenfänre": "Kohlensäure",
    "Kohlcnsäure": "Kohlensäure",
    "Kohlenstoffs": "Kohlenstoffs",
    "Wasserstoffs": "Wasserstoffs",
    "Stickstoffs": "Stickstoffs",
    "Schwefels": "Schwefels",
    "Schwefelkies": "Schwefelkies",
    "Eifcn": "Eisen",
    "Eifen": "Eisen",
    "Kiefel": "Kiesel",
    "Queckfilber": "Quecksilber",
    "Nervenfjftem": "Nervensystem",
    "Nervenfyftem": "Nervensystem",
    "Nervenfystem": "Nervensystem",
    "Eingeweidefjftem": "Eingeweidesystem",
    "Galvanifmus": "Galvanismus",
    "Elektrifmus": "Elektrismus",
    "Magnetifmus": "Magnetismus",
    "Mesmerifmus": "Mesmerismus",
    "Meamerismns": "Mesmerismus",
    "Meamerismus": "Mesmerismus",
    "Mefmerismus": "Mesmerismus",
    "Organifmus": "Organismus",
    "organifche": "organische",
    "Organifche": "Organische",
    "organifchen": "organischen",
    "organifcher": "organischer",
    "anorganifche": "anorganische",
    "anorganifchen": "anorganischen",
    "Kryftallisation": "Krystallisation",
    "Kryftallisationstheorie": "Krystallisationstheorie",
    "Krystallisaiionstheorie": "Krystallisationstheorie",
    "kryftallinifch": "krystallinisch",

    # Botany/Zoology
    "Pflanze": "Pflanze",
    "Pflanzen": "Pflanzen",
    "Pflanzennerven": "Pflanzennerven",
    "Spiralfafern": "Spiralfasern",
    "Spiralfafer": "Spiralfaser",
    "Mufkel": "Muskel",
    "Mufkeln": "Muskeln",
    "Gefäfse": "Gefäße",
    "Gefäfs": "Gefäß",
    "Gefäfssystem": "Gefäßsystem",

    # Common word endings with -ifs/-nis/-ung
    "Erkenntnifs": "Erkenntniß",
    "Kenntnifs": "Kenntniß",
    "Kenntnifse": "Kenntnisse",
    "Finsternifs": "Finsterniß",
    "Wissenschaft": "Wissenschaft",
    "Wiffenschaft": "Wissenschaft",
    "Wifsenschaften": "Wissenschaften",
    "Wiffenschaften": "Wissenschaften",
    "Naturphilofophie": "Naturphilosophie",
    "Naturphilosophie": "Naturphilosophie",
    "Philofophie": "Philosophie",
    "philofophifch": "philosophisch",
    "Gefchichte": "Geschichte",
    "gefchichtlich": "geschichtlich",

    # -sch- cluster (fch → sch)
    "Menfch": "Mensch",
    "Menfchen": "Menschen",
    "menfchlich": "menschlich",
    "menfchliche": "menschliche",
    "menfchlichen": "menschlichen",
    "Menfchheit": "Menschheit",
    "Thierreich": "Thierreich",
    "Pflanzenreich": "Pflanzenreich",
    "Mineralreich": "Mineralreich",
    "Wiffenfchaft": "Wissenschaft",
    "wiffenfchaftlich": "wissenschaftlich",
    "Herrfchaft": "Herrschaft",
    "Gefellfchaft": "Gesellschaft",
    "Eigenfchaft": "Eigenschaft",
    "Eigenfchaften": "Eigenschaften",
    "Befchaffenheit": "Beschaffenheit",
    "verfchieden": "verschieden",
    "Verfchiedene": "Verschiedene",
    "verfchiedene": "verschiedene",
    "verfchiedenen": "verschiedenen",
    "Verfchiedenheit": "Verschiedenheit",
    "Erfcheinung": "Erscheinung",
    "Erfcheinungen": "Erscheinungen",
    "Gcfchlecht": "Geschlecht",
}

# Regex pattern for "Digitized by Google" variants — very broad to catch OCR mangling
DIGITIZED_RE = re.compile(
    r"(?:igiti|oogle|OOQ|jOOQ|VnOO|CjO|ogle|Djgit|igitiz|Digit)",
    re.IGNORECASE,
)

# Scanner artifact lines (just symbols, page numbers, etc.)
ARTIFACT_RE = re.compile(
    r"^[\s\.\,\;\:\'\"\-\*\•\■\▼\^\~\#\!\?\(\)\[\]\{\}\<\>\|\/"
    r"\d\u2019\u201c\u201d\u2018\u00ab\u00bb]+$"
)

# Roman numeral page markers (standalone)
ROMAN_RE = re.compile(r"^\s*[IVXLCDM]{1,6}\s*$")

# Page number lines (just digits, possibly with dots)
PAGENUM_RE = re.compile(r"^\s*\.?\s*\d{1,4}\s*\.?\s*$")


def clean_line(line: str) -> str | None:
    """Clean a single line. Returns None if the line should be dropped."""

    # Strip trailing whitespace
    line = line.rstrip()

    # Drop empty/near-empty lines (keep for paragraph detection, filter later)
    if not line.strip():
        return ""

    # Drop "Digitized by Google" watermarks (broad match)
    if DIGITIZED_RE.search(line):
        return None

    # Drop scanner artifact lines
    stripped = line.strip()
    if ARTIFACT_RE.match(stripped) and len(stripped) < 20:
        return None

    # Drop standalone Roman numerals (page numbers)
    if ROMAN_RE.match(stripped):
        return None

    # Drop standalone page numbers
    if PAGENUM_RE.match(stripped):
        return None

    # Convert HTML entities
    line = html.unescape(line)

    # Remove common scanner noise characters
    line = line.replace("▼", "").replace("■", "").replace("•", "")
    line = line.replace("^", "").replace("~", "")

    # Fix spaced-out letters in headings (e.g., "W a s s e r" → "Wasser")
    # Only for lines that are mostly spaced single characters
    words = line.strip().split()
    if len(words) >= 3:
        single_chars = sum(1 for w in words if len(w) == 1 and w.isalpha())
        if single_chars > len(words) * 0.6 and len(words) <= 20:
            # Reconstruct: join single chars, keep multi-char words
            result = []
            buffer = []
            for w in words:
                if len(w) == 1 and w.isalpha():
                    buffer.append(w)
                else:
                    if buffer:
                        result.append("".join(buffer))
                        buffer = []
                    result.append(w)
            if buffer:
                result.append("".join(buffer))
            line = " ".join(result)

    return line


def apply_word_fixes(text: str) -> str:
    """Apply word-level Fraktur OCR fixes."""
    for wrong, right in WORD_FIXES.items():
        # Use word boundary matching to avoid partial replacements
        pattern = r'\b' + re.escape(wrong) + r'\b'
        text = re.sub(pattern, right, text)
    return text


def apply_fch_sch_fix(text: str) -> str:
    """Fix the very common fch → sch OCR error in German."""
    # This is one of the most reliable patterns: "fch" is almost always "sch" in German
    text = re.sub(r'\bfch', 'sch', text)
    text = re.sub(r'\bFch', 'Sch', text)
    # Also mid-word fch → sch (e.g., "Wiffenfchaft")
    text = text.replace('fch', 'sch')
    return text


def apply_fs_ss_fix(text: str) -> str:
    """Fix common -fs- patterns that should be -ss- or -ß-."""
    # "fs" at end of word often = "ß" (e.g., "dafs" → "daß")
    # Be conservative — only fix known safe patterns
    text = re.sub(r'(\w)fs\b', r'\1ß', text)
    # "ff" that should be "ss" in some contexts
    # Only fix known patterns, not blanket replacement
    return text


def rejoin_hyphenated(lines: list[str]) -> list[str]:
    """Rejoin words hyphenated across line breaks."""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if line ends with a hyphen and next line starts with a word
        if (line and line.rstrip().endswith("-")
            and i + 1 < len(lines)
            and lines[i + 1]
            and lines[i + 1].strip()
            and lines[i + 1].strip()[0].isalpha()):
            # Join the hyphenated word
            next_line = lines[i + 1].strip()
            line = line.rstrip()[:-1] + next_line
            i += 2
        else:
            i += 1
        result.append(line)
    return result


def collapse_blank_lines(lines: list[str], max_consecutive: int = 2) -> list[str]:
    """Collapse runs of blank lines to at most max_consecutive."""
    result = []
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= max_consecutive:
                result.append("")
        else:
            blank_count = 0
            result.append(line)
    return result


def find_body_start(lines: list[str]) -> int:
    """Find where the actual body text begins (after front matter/TOC)."""
    # Look for "Einleitung" (Introduction) which signals start of body
    for i, line in enumerate(lines):
        if "Einleitung" in line and i > 50:
            return max(0, i - 1)
    # Fallback: skip first 200 lines
    return 200


def main():
    print(f"Reading {INPUT}...")
    raw = INPUT.read_text(encoding="utf-8")
    lines = raw.split("\n")
    print(f"  {len(lines)} raw lines")

    # Phase 1: Clean individual lines
    print("Phase 1: Cleaning individual lines...")
    cleaned = []
    dropped = 0
    for line in lines:
        result = clean_line(line)
        if result is None:
            dropped += 1
        else:
            cleaned.append(result)
    print(f"  Dropped {dropped} lines (watermarks, artifacts, page numbers)")

    # Phase 2: Find and skip front matter
    print("Phase 2: Skipping front matter...")
    body_start = find_body_start(cleaned)
    print(f"  Body starts at line {body_start}")
    cleaned = cleaned[body_start:]

    # Phase 3: Rejoin hyphenated words
    print("Phase 3: Rejoining hyphenated words...")
    cleaned = rejoin_hyphenated(cleaned)

    # Phase 4: Apply Fraktur OCR fixes
    print("Phase 4: Applying Fraktur OCR fixes...")
    text = "\n".join(cleaned)

    # Apply specific word fixes first (most reliable)
    text = apply_word_fixes(text)

    # Apply fch → sch fix (very reliable pattern)
    text = apply_fch_sch_fix(text)

    # Phase 5: Collapse blank lines
    print("Phase 5: Collapsing blank lines...")
    lines = text.split("\n")
    lines = collapse_blank_lines(lines, max_consecutive=1)

    # Phase 6: Strip leading/trailing whitespace from each line
    lines = [line.strip() for line in lines]

    # Final cleanup: remove any remaining very short garbage lines
    final_lines = []
    for line in lines:
        # Keep blank lines (paragraph breaks) and substantive lines
        if not line:
            final_lines.append(line)
        elif len(line) >= 3 or line[0].isdigit():
            final_lines.append(line)
        # Drop 1-2 char non-digit lines (scanner noise)

    # Write output
    output_text = "\n".join(final_lines).strip() + "\n"
    OUTPUT.write_text(output_text, encoding="utf-8")

    line_count = len(final_lines)
    char_count = len(output_text)
    word_count = len(output_text.split())
    print(f"\nOutput: {OUTPUT}")
    print(f"  {line_count} lines")
    print(f"  {word_count:,} words")
    print(f"  {char_count:,} characters")
    print(f"  {char_count / 1024:.0f} KB")

    # Show a sample of the cleaned text
    print(f"\n{'='*60}")
    print("SAMPLE (first 30 lines of body):")
    print(f"{'='*60}")
    for line in final_lines[:30]:
        print(f"  {line}")

    print(f"\n{'='*60}")
    print("SAMPLE (around line 500):")
    print(f"{'='*60}")
    for line in final_lines[500:530]:
        print(f"  {line}")


if __name__ == "__main__":
    main()
