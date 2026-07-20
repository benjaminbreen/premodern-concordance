from __future__ import annotations

import unittest

from premodern.findings import validate_findings


class FindingValidationTest(unittest.TestCase):
    def test_findings_are_closed_over_grounded_claims(self) -> None:
        findings = validate_findings(
            {
                "findings": [
                    {
                        "finding_type": "DISAGREEMENT",
                        "title": "Opposed accounts of efficacy",
                        "summary": "One author asserts efficacy while another denies it.",
                        "claim_links": [
                            {"claim_id": "claim-a", "role": "SUPPORTS"},
                            {"claim_id": "claim-b", "role": "CONTRADICTS"},
                        ],
                        "confidence": 0.9,
                    }
                ]
            },
            ["claim-a", "claim-b"],
        )
        self.assertEqual(findings[0]["finding_type"], "DISAGREEMENT")

        with self.assertRaisesRegex(ValueError, "unknown claim"):
            validate_findings(
                {
                    "findings": [
                        {
                            "finding_type": "RECURRENCE",
                            "title": "Repeated claim",
                            "summary": "The claim recurs.",
                            "claim_links": [
                                {"claim_id": "claim-a", "role": "EXAMPLE"},
                                {"claim_id": "invented", "role": "EXAMPLE"},
                            ],
                            "confidence": 0.8,
                        }
                    ]
                },
                ["claim-a", "claim-b"],
            )

        with self.assertRaisesRegex(ValueError, "supporting and contradicting"):
            validate_findings(
                {
                    "findings": [
                        {
                            "finding_type": "DISAGREEMENT",
                            "title": "Not actually opposed",
                            "summary": "Both claims support the same account.",
                            "claim_links": [
                                {"claim_id": "claim-a", "role": "SUPPORTS"},
                                {"claim_id": "claim-b", "role": "SUPPORTS"},
                            ],
                            "confidence": 0.5,
                        }
                    ]
                },
                ["claim-a", "claim-b"],
            )


if __name__ == "__main__":
    unittest.main()
