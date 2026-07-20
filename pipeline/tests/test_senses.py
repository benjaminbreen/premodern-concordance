from __future__ import annotations

import unittest

from premodern.senses import repair_duplicate_assignments, validate_senses


class SenseValidationTest(unittest.TestCase):
    def test_closed_set_assigns_every_usage_once(self) -> None:
        senses = validate_senses(
            {
                "senses": [
                    {
                        "label": "Biological development",
                        "definition": "Development of living forms from simpler to differentiated states.",
                        "usage_ids": ["usage-a", "usage-b"],
                        "confidence": 0.9,
                    },
                    {
                        "label": "Social development",
                        "definition": "Increasing differentiation in social organization.",
                        "usage_ids": ["usage-c"],
                        "confidence": 0.8,
                    },
                ]
            },
            ["usage-a", "usage-b", "usage-c"],
        )
        self.assertEqual(len(senses), 2)

        with self.assertRaisesRegex(ValueError, "not assigned"):
            validate_senses(
                {
                    "senses": [
                        {
                            "label": "Biological development",
                            "definition": "One sense.",
                            "usage_ids": ["usage-a"],
                            "confidence": 0.9,
                        }
                    ]
                },
                ["usage-a", "usage-b"],
            )

        with self.assertRaisesRegex(ValueError, "more than one"):
            duplicate = {
                    "senses": [
                        {
                            "label": "One",
                            "definition": "First sense.",
                            "usage_ids": ["usage-a"],
                            "confidence": 0.9,
                        },
                        {
                            "label": "Two",
                            "definition": "Second sense.",
                            "usage_ids": ["usage-a", "usage-b"],
                            "confidence": 0.8,
                        },
                    ]
                }
            validate_senses(duplicate, ["usage-a", "usage-b"])
        repaired = validate_senses(
            repair_duplicate_assignments(duplicate),
            ["usage-a", "usage-b"],
        )
        self.assertEqual(repaired[0]["usage_ids"], ["usage-a"])
        self.assertEqual(repaired[1]["usage_ids"], ["usage-b"])


if __name__ == "__main__":
    unittest.main()
