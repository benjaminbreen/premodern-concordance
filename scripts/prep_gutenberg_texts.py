#!/usr/bin/env python3
"""
Clean downloaded Gutenberg texts: strip headers/footers, extract
relevant sections for the Premodern Concordance.
"""

import re
from pathlib import Path

TEXTS_DIR = Path(__file__).parent.parent / "web" / "public" / "texts"


def strip_gutenberg(text: str) -> str:
    """Remove Project Gutenberg header and footer."""
    # Find start marker
    start_markers = [
        r"\*\*\* START OF THE PROJECT GUTENBERG EBOOK .+? \*\*\*",
        r"\*\*\* START OF THIS PROJECT GUTENBERG EBOOK .+? \*\*\*",
    ]
    for marker in start_markers:
        m = re.search(marker, text)
        if m:
            text = text[m.end():]
            break

    # Find end marker
    end_markers = [
        r"\*\*\* END OF THE PROJECT GUTENBERG EBOOK .+? \*\*\*",
        r"\*\*\* END OF THIS PROJECT GUTENBERG EBOOK .+? \*\*\*",
    ]
    for marker in end_markers:
        m = re.search(marker, text)
        if m:
            text = text[:m.start()]
            break

    return text.strip()


def extract_pseudodoxia(text: str) -> str:
    """Extract Pseudodoxia Epidemica from the Works of Sir Thomas Browne Vol 1.

    The volume contains Religio Medici first, then Pseudodoxia.
    """
    # Find the start of Pseudodoxia
    m = re.search(r"PSEUDODOXIA EPIDEMICA", text)
    if m:
        text = text[m.start():]

    # The volume ends with Pseudodoxia (it's Volume 1), so just take everything
    # after the header. But remove any trailing Gutenberg content.
    # Check if there's another major work after it
    end_markers = [
        r"\n\s*RELIGIO MEDICI",  # shouldn't appear after, but just in case
        r"\n\s*HYDRIOTAPHIA",
        r"\n\s*THE GARDEN OF CYRUS",
        r"\n\s*CHRISTIAN MORALS",
        r"\n\s*A LETTER TO A FRIEND",
    ]
    for marker in end_markers:
        m2 = re.search(marker, text[1000:])  # Skip past the title
        if m2:
            text = text[:m2.start() + 1000]
            break

    return text.strip()


def clean_kosmos(text: str) -> str:
    """Clean up Kosmos text — remove page markers and transcription notes."""
    # Remove "This material taken from pages X-Y" lines
    text = re.sub(r"This material taken from pages? [\d\-ivx, and]+\n?", "", text)
    # Remove "NB - The page numbers..." lines
    text = re.sub(r"NB - The page numbers.*\n?", "", text)
    # Remove page number lines (standalone numbers)
    text = re.sub(r"\n\s*\d{1,3}\s*\n", "\n", text)
    return text.strip()


def main():
    # Spencer
    raw = (TEXTS_DIR / "first_principles_spencer_1862_raw.txt").read_text(encoding="utf-8")
    clean = strip_gutenberg(raw)
    out = TEXTS_DIR / "first_principles_spencer_1862.txt"
    out.write_text(clean, encoding="utf-8")
    print(f"Spencer: {len(clean):,} chars → {out.name}")

    # Somerville
    raw = (TEXTS_DIR / "connexion_physical_sciences_somerville_1858_raw.txt").read_text(encoding="utf-8")
    clean = strip_gutenberg(raw)
    out = TEXTS_DIR / "connexion_physical_sciences_somerville_1858.txt"
    out.write_text(clean, encoding="utf-8")
    print(f"Somerville: {len(clean):,} chars → {out.name}")

    # Browne — extract Pseudodoxia only
    raw = (TEXTS_DIR / "pseudodoxia_epidemica_browne_1646_raw.txt").read_text(encoding="utf-8")
    clean = strip_gutenberg(raw)
    pseudo = extract_pseudodoxia(clean)
    out = TEXTS_DIR / "pseudodoxia_epidemica_browne_1646.txt"
    out.write_text(pseudo, encoding="utf-8")
    print(f"Browne (Pseudodoxia only): {len(pseudo):,} chars → {out.name}")

    # Kosmos
    raw = (TEXTS_DIR / "kosmos_humboldt_1845_raw.txt").read_text(encoding="utf-8")
    clean = strip_gutenberg(raw)
    clean = clean_kosmos(clean)
    out = TEXTS_DIR / "kosmos_humboldt_1845.txt"
    out.write_text(clean, encoding="utf-8")
    print(f"Kosmos: {len(clean):,} chars → {out.name}")

    # Cleanup raw files
    for f in TEXTS_DIR.glob("*_raw.txt"):
        f.unlink()
        print(f"  Removed {f.name}")

    print("\nDone!")


if __name__ == "__main__":
    main()
