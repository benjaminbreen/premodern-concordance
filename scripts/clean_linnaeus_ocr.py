#!/usr/bin/env python3
"""
Clean OCR text of Linnaeus, Systema Naturae, 10th edition (1758).
Source: 1894 Wilhelm Engelmann facsimile reprint, scanned by NCSU Libraries.

Structure of raw file (~52,668 lines):
  Lines 1-119:       Publisher catalog (German, Engelmann 1894 advertisements)
  Lines 120-180:     Reprint title page
  Lines 182-250:     Dedication to Count Tessin
  Lines 251-400:     Ratio Editionis + Imperium Naturae (introduction)
  Lines 400-51595:   Main body: Mammalia, Aves, Amphibia, Pisces, Insecta, Vermes
  Lines 51597-51715: Appendix (additional species)
  Lines 51721-52000: Emendanda (errata corrections)
  Lines 52000-52668: Publisher catalog (German, Engelmann advertisements)

Cleanup:
  1. Remove publisher catalogs (beginning and end)
  2. Remove errata section (EMENDANDA)
  3. Remove running page headers (e.g., "AVES GALLINÆ. Tetrao 161")
  4. Remove standalone page numbers
  5. Remove signature marks (e.g., "Bb 2", "Fff", "A 3")
  6. Remove short garbled lines (OCR artifacts)
  7. Collapse excessive blank lines
"""

import re
from pathlib import Path

INPUT = Path("books/systema_naturae_linnaeus_1758_raw.txt")
OUTPUT = Path("books/systema_naturae_linnaeus_1758.txt")

# ── Patterns ──

# Running page headers: "MAMMALIA PRIMATES. Homo." or "AVES GALLINÆ. Tetrao" etc.
# Format: CLASS_NAME ORDER_NAME. Genus. [page_number]
PAGE_HEADER_RE = re.compile(
    r'^\s*\d*\s*'
    r'(?:MAMMALIA|AVES|AMPHIBIA|PISCES|INSECTA|VERMES)'
    r'[\s\.]+(?:PRIMATES|BRUTA|FER[AÆ]|GLIRES|PECORA|BELL[UV]'
    r'|CETE|ACCIPITRES|PIC[AÆ]|ANSERES|GRALL[AÆ]|GALLIN[AÆ]'
    r'|PASSERES|REPTILES|SERPENTES|NANTES|APODES|JUGULARES'
    r'|THORACICI|ABDOMINALES|BRANCHIOSTEGI|CHONDROPTERYGII'
    r'|COLEOPTERA|HEMIPTERA|LEPIDOPTERA|NEUROPTERA|HYMENOPTERA'
    r'|DIPTERA|APTERA|INTESTINA|MOLLUSCA|TESTACEA|LITHOPHYTA'
    r'|ZOOPHYTA)',
    re.IGNORECASE
)

# Also catch simpler headers that are just "ORDER. Genus. pagenumber"
SIMPLE_HEADER_RE = re.compile(
    r'^\s*\d{1,3}\s+(?:MAMMALIA|AVES|AMPHIBIA|PISCES|INSECTA|VERMES)\b'
)

# Standalone page numbers
PAGE_NUM_RE = re.compile(r'^\s*\d{1,3}\s*$')

# Signature marks: "A 3", "Bb 2", "Fff", "Cc 2" etc.
SIGNATURE_RE = re.compile(r'^\s*[A-Z][a-z]{0,2}\s*\d?\s*$')

# Publisher catalog indicators (German text from Engelmann)
PUBLISHER_RE = re.compile(
    r'(?:Verlag\s+von|Wilhelm\s+Engel|Bibliotheca\s+zoo|'
    r'Bearbeitet\s+von|Bisher\s+erschien|Herabgesetzter\s+Preis|'
    r'In\s+Vorbereitung|Schlussband|Lieferung|Holzschnitt|'
    r'geh\.\s*[Jj]|cart\.\s*[Jj]|Druck\s+von\s+Breitkopf|'
    r'PROPER|METCALF|Monographic\s+der|Entwickelungsgeschichte|'
    r'Gemeinverstandliche|Privatdocenten|Darwinschen\s+Theorie|'
    r'Professor\s+an\s+der\s+Universitat|Zweite\s+vermehrte\s+Auflage|'
    r'Eine\s+kritische\s+Studie|Leitfaden\s+bei)',
    re.IGNORECASE
)

# EMENDANDA errata entries: "pag. 52  lin. 1" etc.
EMENDANDA_RE = re.compile(r'^\s*(?:pag\.?|lin\.?|\d+\s+—|\s*—\s*\d)')

# Short lines that are likely OCR artifacts (≤3 alphanumeric chars)
def is_garbled_short(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    alpha = sum(1 for c in stripped if c.isalnum())
    if alpha > 4:
        return False
    # Keep lines that start with numbers followed by a period (species entries like "2. L.")
    if re.match(r'^\d+\.\s', stripped):
        return False
    # Keep footnote markers
    if re.match(r'^\(\w\)', stripped):
        return False
    return len(stripped) <= 5


def clean_linnaeus():
    raw = INPUT.read_text(encoding='utf-8')
    lines = raw.splitlines()
    total = len(lines)
    print(f"Input: {total} lines")

    # ── Phase 1: Find section boundaries ──
    # Publisher catalog at start: ends around line 119 (before second title page)
    catalog_end = 0
    for i, line in enumerate(lines):
        if 'CAROLI' in line and 'LINN' in line and i > 50:
            catalog_end = i
            break

    # Find EMENDANDA section
    emendanda_start = None
    for i, line in enumerate(lines):
        if 'EMENDANDA' in line.strip():
            emendanda_start = i
            break

    # Find publisher catalog at end: starts with German text after the body
    catalog_start_end = total
    for i in range(total - 1, max(total - 1000, 0), -1):
        stripped = lines[i].strip()
        if PUBLISHER_RE.search(stripped):
            # Scan backwards to find start of catalog block
            for j in range(i, max(i - 200, 0), -1):
                sj = lines[j].strip()
                if 'Lipfiae' in sj or 'Lipsiae' in sj or 'typis' in sj.lower():
                    catalog_start_end = j
                    break
            if catalog_start_end == total:
                catalog_start_end = i - 10
            break

    # Also check: the main text's last meaningful line
    # After "EMENDANDA" and errata, publisher ads start
    if emendanda_start:
        catalog_start_end = min(catalog_start_end, emendanda_start)

    print(f"Publisher catalog ends: line {catalog_end}")
    print(f"Body text ends / publisher ads start: line {catalog_start_end}")

    # ── Phase 2: Process lines ──
    output = []
    skipped_catalog = 0
    skipped_header = 0
    skipped_garbled = 0
    skipped_pagenum = 0
    skipped_emendanda = 0

    in_emendanda = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip publisher catalog at start
        if i < catalog_end:
            skipped_catalog += 1
            continue

        # Skip everything after body text ends
        if i >= catalog_start_end:
            skipped_catalog += 1
            continue

        # Skip EMENDANDA section
        if emendanda_start and i >= emendanda_start:
            skipped_emendanda += 1
            continue

        # Skip running page headers
        if stripped and PAGE_HEADER_RE.match(stripped):
            skipped_header += 1
            continue
        if stripped and SIMPLE_HEADER_RE.match(stripped):
            skipped_header += 1
            continue

        # Skip standalone page numbers (when surrounded by blanks)
        if PAGE_NUM_RE.match(stripped):
            prev_blank = (i == 0 or not lines[i-1].strip())
            next_blank = (i >= total-1 or not lines[i+1].strip())
            if prev_blank or next_blank:
                skipped_pagenum += 1
                continue

        # Skip signature marks
        if stripped and SIGNATURE_RE.match(stripped):
            # But don't skip single capital letters that could be section headers
            if not re.match(r'^[A-Z]\.$', stripped):
                skipped_garbled += 1
                continue

        # Skip garbled short lines
        if stripped and is_garbled_short(stripped):
            skipped_garbled += 1
            continue

        output.append(line)

    # ── Phase 3: Collapse excessive blank lines ──
    collapsed = []
    blank_count = 0
    for line in output:
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:
                collapsed.append('')
        else:
            blank_count = 0
            collapsed.append(line)

    while collapsed and not collapsed[-1].strip():
        collapsed.pop()

    # ── Phase 4: Write output ──
    result = '\n'.join(collapsed) + '\n'
    OUTPUT.write_text(result, encoding='utf-8')

    out_lines = len(collapsed)
    out_words = len(result.split())

    print(f"\nResults:")
    print(f"  Skipped publisher catalog: {skipped_catalog}")
    print(f"  Skipped page headers:      {skipped_header}")
    print(f"  Skipped page numbers:      {skipped_pagenum}")
    print(f"  Skipped emendanda:         {skipped_emendanda}")
    print(f"  Skipped garbled/short:     {skipped_garbled}")
    print(f"  Output: {out_lines} lines, {out_words} words")
    print(f"  Written to: {OUTPUT}")


if __name__ == '__main__':
    clean_linnaeus()
