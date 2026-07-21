"""
Tests del conector AWS Cost Explorer. Usan un cliente boto3 mockeado
(unittest.mock) — así se testean conectores cloud: nunca contra la API
real en un test unitario. Requieren boto3 instalado para poder importar
el módulo bajo test (ver requirements en pyproject.toml).
"""

import unittest
from unittest.mock import MagicMock

from sicg.config import AWSConfig
from sicg.ingestion.aws_cost import AWSCostSource


class TestAWSCostSource(unittest.TestCase):
    def _make_source(self):
        fake_client = MagicMock()
        source = AWSCostSource(config=AWSConfig(region="eu-west-1"), client=fake_client)
        return source, fake_client

    def test_parses_grouped_response_into_cost_events(self):
        source, fake_client = self._make_source()
        fake_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-07-19", "End": "2026-07-20"},
                    "Groups": [
                        {
                            "Keys": ["arn:aws:iam::111122223333:user/jgarcia", "EC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "12.34"}},
                        },
                        {
                            "Keys": ["arn:aws:iam::111122223333:user/mrodriguez", "S3"],
                            "Metrics": {"UnblendedCost": {"Amount": "3.10"}},
                        },
                    ],
                }
            ]
        }

        events = source.fetch_cost_events()

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].identity_id, "arn:aws:iam::111122223333:user/jgarcia")
        self.assertEqual(events[0].service, "ec2")
        self.assertEqual(events[0].amount_usd, 12.34)

    def test_skips_zero_or_negative_amounts(self):
        source, fake_client = self._make_source()
        fake_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-07-19", "End": "2026-07-20"},
                    "Groups": [
                        {
                            "Keys": ["arn:aws:iam::111122223333:user/jgarcia", "EC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "0.00"}},
                        }
                    ],
                }
            ]
        }

        events = source.fetch_cost_events()
        self.assertEqual(len(events), 0)

    def test_strips_cost_allocation_tag_prefix_from_identity(self):
        source, fake_client = self._make_source()
        fake_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-07-19", "End": "2026-07-20"},
                    "Groups": [
                        {
                            "Keys": [
                                "aws:createdBy$AWSAssumedRole$arn:aws:sts::111122223333:assumed-role/deploy/session",
                                "Lambda",
                            ],
                            "Metrics": {"UnblendedCost": {"Amount": "5.00"}},
                        }
                    ],
                }
            ]
        }

        events = source.fetch_cost_events()
        self.assertEqual(
            events[0].identity_id,
            "arn:aws:sts::111122223333:assumed-role/deploy/session",
        )

    def test_propagates_client_errors(self):
        from botocore.exceptions import ClientError

        source, fake_client = self._make_source()
        fake_client.get_cost_and_usage.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "GetCostAndUsage",
        )

        with self.assertRaises(ClientError):
            source.fetch_cost_events()


if __name__ == "__main__":
    unittest.main()
