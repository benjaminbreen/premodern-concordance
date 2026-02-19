#!/usr/bin/env python3
"""
Clean OCR text of Piso & Marcgrave, Historia Naturalis Brasiliae (1648).

Source: Archive.org / Biblioteca Digital Curt Nimuendaju
OCR from Google Books / Missouri Botanical Garden scan.

Structure of the raw file (~39K lines):
  Lines 1-200:     Front matter (Portuguese library metadata, garbled title page)
  Lines 200-600:   Dedication + preface + table of contents (Latin)
  Lines 600-9567:  Piso's De Medicina Brasiliensi (main medical text)
  Lines 9568-~10500: First index (Rerum et Verborum) — page number lists
  Lines 10500-29500: Marcgrave's Historia Naturalis (plants, fish, birds, etc.)
  Lines 29500-35100: Liber Octavus (geography, ethnography) — interspersed with
                      meteorological wind direction tables
  Lines 35100-36044: End of ethnography text (Tapuys, Chileans)
  Lines 36045-38925: Second index (Plantarum et Animantium) — page number lists
  Lines 38925+:     FINIS + conservation notes

Cleanup strategy:
  1. Strip Portuguese front matter (lines 1-200)
  2. Strip both indexes (page number lists, not useful for entity extraction)
  3. Strip meteorological wind-direction tables
  4. Strip conservation notes at end
  5. Remove page headers/footers (running headers, page numbers)
  6. Remove OCR artifacts (garbled fragments, single-character lines)
  7. Collapse excessive blank lines
"""

import re
import sys
from pathlib import Path

INPUT = Path("books/piso_historia_brasiliae_1648_raw.txt")
OUTPUT = Path("books/piso_historia_naturalis_brasiliae_1648.txt")

# ── Patterns ──

# Page headers: lines like "de Medicina Brasil. Lib. t. 5" or "GeorgI MarcgravI"
# or "Histor. Plantarvm Lib. II." or "Gviliulmi Pisonis" etc.
PAGE_HEADER_RE = re.compile(
    r'^\s*('
    r'de\s+Medicina\s+Brasil|'
    r'De\s+Medicina\s+Brasil|'
    r'DE\s+MEDICINA\s+BRASIL|'
    r'Georgi?\s*I?\s*Marc?grav|'
    r'GEORGI?\s*I?\s*MARCGRAV|'
    r'Gviliulmi\s+Piso|'
    r'GVILIULMI\s+PISO|'
    r'G\s*V\s*I\s*L\s*I\s*E\s*L\s*M\s*I\s+P\s*[Ii]\s*S\s*O|'
    r'Histor\.\s*Plantarvm|'
    r'HISTOR\.\s*PLANTARVM|'
    r'Histor\.\s*Qvadrvped|'
    r'HISTOR\.\s*QVADRVPED|'
    r'de\s+Insectis\s+Lib|'
    r'DE\s+INSECTIS\s+LIB|'
    r'de\s+ipsa\s+Regione|'
    r'DE\s+IPSA\s+REGIONE|'
    r'bE\s+ipsa\s+Regions|'  # OCR variant
    r'DE\s+IPSA.*REGIONS|'
    r'de\s+Avibvs\s+Lib|'
    r'DE\s+AVIBVS\s+LIB|'
    r'de\s+Piscibvs\s+Lib|'
    r'DE\s+PISCIBVS\s+LIB|'
    r'Index\s+Rervm\s+et\s+Ver|'
    r'INDEX\s+RERVM|'
    r'ARVM\s+ET\s+ANIMANTIVM'
    r')\s*', re.IGNORECASE
)

# Wind direction table lines (compass abbreviations)
WIND_RE = re.compile(
    r'^\s*'
    r'(?:p\.?\s*)?'                   # optional "p." prefix
    r'(?:N\.?O\.?|S\.?O\.?|N\.?|S\.?|O\.?|V\.?|'
    r'O\.?N\.?|O\.?S\.?|S\.?S\.?|N\.?N\.?|'
    r's\.o\.?|p-|P-|id\.?)'
    r'\s*$'
)

# Standalone page numbers
PAGE_NUM_RE = re.compile(r'^\s*\d{1,3}\s*$')

# Very short garbled lines (1-3 chars, likely OCR artifacts)
GARBLED_SHORT_RE = re.compile(r'^\s*[^\w\s]{0,1}\w{0,2}[^\w\s]{0,1}\s*$')

# Lines that are just punctuation/symbols
SYMBOL_LINE_RE = re.compile(r'^[\s\^\$\*\#\&\|\[\]\{\}\(\)\<\>\\\/\.\,\;\:\!\?\-\_\+\=\~\`\'\"]+$')

# Index entry: "Plantname page_number" or "Plantname ibid." patterns
# (term followed by isolated number at line end, or "ibid.")
INDEX_ENTRY_RE = re.compile(r'^\s*\w+.*\s+\d{1,3}\s*$')

# Month table headers
MONTH_TABLE_RE = re.compile(
    r'^\s*(?:f?\s*Ian|Feb|Mar|Apr|Ma[ij]|[Ii]un|[Ii]ul|Aug|Sept|Oct|Nov|Dec)'
    r'[\.\s]*$', re.IGNORECASE
)


def is_wind_table_line(line: str) -> bool:
    """Check if line is a meteorological wind-direction table entry."""
    stripped = line.strip()
    if not stripped:
        return False
    return bool(WIND_RE.match(stripped))


def is_standalone_number(line: str) -> bool:
    """Lines that are just page numbers (1-3 digits)."""
    return bool(PAGE_NUM_RE.match(line.strip()))


def is_garbled_short(line: str) -> bool:
    """Very short lines (≤3 non-space chars) that are OCR garbage."""
    stripped = line.strip()
    if not stripped:
        return False
    # Only filter lines with ≤ 3 actual characters
    alpha_chars = sum(1 for c in stripped if c.isalnum())
    if alpha_chars > 3:
        return False
    # But keep lines that look like Roman numerals, section markers
    if re.match(r'^[IVXLC]+\.?$', stripped):
        return False
    # Keep "A." "B." etc. (alphabetical section headers)
    if re.match(r'^[A-Z]\.\s*$', stripped):
        return False
    return len(stripped) <= 4


def is_page_header(line: str) -> bool:
    """Running page headers like 'GeorgI MarcgravI' or page number + header."""
    stripped = line.strip()
    if not stripped:
        return False
    # Check for page number prefix (e.g., "254 , GeorgI MarcgravI")
    no_num = re.sub(r'^\d+[\s,\.]*', '', stripped)
    if PAGE_HEADER_RE.match(no_num):
        return True
    if PAGE_HEADER_RE.match(stripped):
        return True
    return False


def clean_piso():
    raw = INPUT.read_text(encoding='utf-8')
    lines = raw.splitlines()
    total = len(lines)
    print(f"Input: {total} lines")

    # ── Phase 1: Identify section boundaries ──
    # Find indexes to skip
    first_index_start = None
    first_index_end = None
    second_index_start = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        upper = stripped.upper()
        # First index: "INDEX RERVM ET VERBORVM" (around line 9570)
        if not first_index_start and 'INDEX' in upper and i < 15000:
            # Check nearby lines for "RERVM" to confirm it's the index heading
            nearby = ' '.join(lines[max(0,i-2):i+3]).upper()
            if 'RERVM' in nearby:
                first_index_start = i - 3
        # First index ends where Marcgrave's title page begins
        # Look for "GeorgI MarcgravI" or "HISTORIC RERVM NATVRALIVM"
        if first_index_start and not first_index_end:
            if 'Marcgrav' in stripped or 'MARCGRAV' in stripped:
                if i > first_index_start + 100:
                    first_index_end = i - 2
        # Second index
        if 'INDEX' in upper and i > 30000:
            if second_index_start is None:
                second_index_start = i - 5

    print(f"First index: lines {first_index_start}-{first_index_end}")
    print(f"Second index starts: line {second_index_start}")

    # Find where actual body text starts (after Portuguese front matter)
    body_start = 200  # Skip Portuguese metadata and garbled title page

    # Find FINIS
    finis_line = total
    for i in range(total - 1, max(total - 200, 0), -1):
        if 'P I N I S' in lines[i] or 'FINIS' in lines[i].strip():
            finis_line = i
            break

    # ── Phase 2: Process lines ──
    output = []
    skipped_front = 0
    skipped_index = 0
    skipped_wind = 0
    skipped_header = 0
    skipped_garbled = 0
    skipped_end = 0

    # Track if we're in an index section
    in_index = False
    # Track consecutive wind-table lines for bulk removal
    wind_run = 0

    i = 0
    while i < total:
        line = lines[i]
        stripped = line.strip()

        # Skip front matter
        if i < body_start:
            skipped_front += 1
            i += 1
            continue

        # Skip after FINIS
        if i >= finis_line:
            skipped_end += 1
            i += 1
            continue

        # Skip first index section
        if first_index_start and first_index_end:
            if first_index_start <= i <= first_index_end:
                skipped_index += 1
                i += 1
                continue

        # Skip second index section
        if second_index_start and i >= second_index_start:
            skipped_index += 1
            i += 1
            continue

        # Skip wind direction table lines
        if is_wind_table_line(stripped):
            skipped_wind += 1
            wind_run += 1
            i += 1
            continue

        # Skip month table headers when near wind tables
        if wind_run > 0 and MONTH_TABLE_RE.match(stripped):
            skipped_wind += 1
            i += 1
            continue

        # Reset wind run counter
        if stripped and not is_standalone_number(stripped):
            wind_run = 0

        # Skip standalone page numbers (but only when not in body text flow)
        if is_standalone_number(stripped):
            # Check context: if surrounded by blank lines or headers, skip
            prev_blank = (i == 0 or not lines[i-1].strip())
            next_blank = (i == total-1 or not lines[i+1].strip())
            if prev_blank or next_blank:
                skipped_garbled += 1
                i += 1
                continue

        # Skip page headers
        if is_page_header(stripped):
            skipped_header += 1
            i += 1
            continue

        # Skip very short garbled lines (≤3 chars)
        if stripped and is_garbled_short(stripped):
            # Don't skip if it looks like part of a sentence
            prev_ends_comma = (i > 0 and lines[i-1].strip().endswith(','))
            if not prev_ends_comma:
                skipped_garbled += 1
                i += 1
                continue

        # Skip pure symbol lines
        if stripped and SYMBOL_LINE_RE.match(stripped):
            skipped_garbled += 1
            i += 1
            continue

        output.append(line)
        i += 1

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

    # Strip trailing blanks
    while collapsed and not collapsed[-1].strip():
        collapsed.pop()

    # ── Phase 4: Write output ──
    result = '\n'.join(collapsed) + '\n'
    OUTPUT.write_text(result, encoding='utf-8')

    out_lines = len(collapsed)
    out_words = len(result.split())

    print(f"\nResults:")
    print(f"  Skipped front matter:  {skipped_front}")
    print(f"  Skipped index lines:   {skipped_index}")
    print(f"  Skipped wind tables:   {skipped_wind}")
    print(f"  Skipped page headers:  {skipped_header}")
    print(f"  Skipped garbled/short: {skipped_garbled}")
    print(f"  Skipped end matter:    {skipped_end}")
    print(f"  Output: {out_lines} lines, {out_words} words")
    print(f"  Written to: {OUTPUT}")


if __name__ == '__main__':
    clean_piso()
