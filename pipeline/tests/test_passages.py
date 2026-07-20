from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from premodern.passages import (
    PassageDraft,
    align_passages,
    page_number_lookup,
    parse_djvu_pages,
    passageize_text,
)


class PassageTests(unittest.TestCase):
    def test_passageization_preserves_non_overlapping_source_slices(self) -> None:
        paragraphs = []
        for paragraph in range(9):
            words = [f"word{paragraph}_{index}" for index in range(55)]
            paragraphs.append(" ".join(words) + ".")
        text = "\n\n".join(paragraphs)

        passages = passageize_text("source-test", text)

        self.assertGreaterEqual(len(passages), 2)
        previous_end = -1
        for sequence, passage in enumerate(passages):
            self.assertEqual(passage.sequence, sequence)
            self.assertGreaterEqual(passage.start_offset, previous_end)
            self.assertEqual(
                passage.raw_text,
                text[passage.start_offset : passage.end_offset],
            )
            self.assertEqual(passage.display_text, passage.raw_text)
            self.assertLessEqual(passage.word_count, 320)
            previous_end = passage.end_offset

    def test_djvu_parser_uses_page_parameter_not_array_position(self) -> None:
        xml = """<?xml version="1.0"?><DjVuXML><BODY>
        <OBJECT><PARAM name="PAGE" value="item_0003.djvu"/>
        <HIDDENTEXT><PAGECOLUMN><REGION><PARAGRAPH><LINE>
        <WORD>alpha</WORD><WORD>beta</WORD><WORD>gamma</WORD><WORD>delta</WORD>
        </LINE></PARAGRAPH></REGION></PAGECOLUMN></HIDDENTEXT></OBJECT>
        </BODY></DjVuXML>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.xml"
            path.write_text(xml, encoding="utf-8")
            pages = parse_djvu_pages(path)
        self.assertEqual(pages[0].leaf, 2)
        self.assertIn("alpha beta gamma delta", pages[0].grams)

    def test_page_numbers_are_converted_from_one_based_leaves(self) -> None:
        payload = {
            "pages": [
                {"leafNum": 6, "pageNumber": "1"},
                {"leafNum": 7, "pageNumber": "2"},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pages.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            lookup = page_number_lookup(path)
        self.assertEqual(lookup(5), "1")
        self.assertEqual(lookup(6), "2")
        self.assertEqual(lookup(7), "3")

    def test_alignment_retains_page_range_and_scan_link(self) -> None:
        xml = """<?xml version="1.0"?><DjVuXML><BODY>
        <OBJECT><PARAM name="PAGE" value="item_0002.djvu"/><HIDDENTEXT>
        <WORD>unique</WORD><WORD>historical</WORD><WORD>medical</WORD><WORD>claim</WORD>
        <WORD>about</WORD><WORD>bark</WORD></HIDDENTEXT></OBJECT>
        </BODY></DjVuXML>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xml_path = root / "item_djvu.xml"
            xml_path.write_text(xml, encoding="utf-8")
            pages = parse_djvu_pages(xml_path)
            passage = PassageDraft(
                id="passage-1",
                source_id="source-1",
                sequence=0,
                start_offset=0,
                end_offset=42,
                raw_text="unique historical medical claim about bark",
                display_text="unique historical medical claim about bark",
                search_text="unique historical medical claim about bark",
            )
            aligned, summary = align_passages(
                [passage],
                pages,
                archive_item_id="item",
                page_numbers_path=None,
            )
        self.assertEqual(summary.directly_aligned_count, 1)
        self.assertEqual(aligned[0].scan_leaf, 1)
        self.assertEqual(aligned[0].scan_leaf_end, 1)
        self.assertEqual(aligned[0].alignment_method, "FOUR_GRAM")
        self.assertIn("/page/n1/", aligned[0].scan_url)


if __name__ == "__main__":
    unittest.main()
