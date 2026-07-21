import unittest
from datetime import datetime
from unittest.mock import MagicMock

from sicg.config import AWSConfig
from sicg.ingestion.aws_iam import AWSIdentitySource
from sicg.normalization.schemas import IdentityEventType


def make_paginator_mock(events_by_call):
    """events_by_call: lista de listas de eventos crudos, una por cada
    llamada a paginate() (una por cada nombre de evento sensible)."""
    paginator = MagicMock()
    call_results = iter(events_by_call)

    def paginate(**kwargs):
        try:
            events = next(call_results)
        except StopIteration:
            events = []
        return [{"Events": events}]

    paginator.paginate.side_effect = paginate
    return paginator


class TestAWSIdentitySource(unittest.TestCase):
    def test_parses_sensitive_events(self):
        fake_client = MagicMock()
        raw_event = {
            "EventTime": datetime(2026, 7, 20, 10, 0, 0),
            "Username": "jgarcia",
            "Resources": [{"ResourceName": "arn:aws:iam::111122223333:user/jgarcia"}],
            "CloudTrailEvent": '{"sourceIPAddress":"203.0.113.5","eventName":"CreateAccessKey"}',
        }
        # el primer nombre sensible que se consulta es AttachUserPolicy en el dict,
        # así que devolvemos el evento en la primera llamada y vacío en las demás
        fake_client.get_paginator.return_value = make_paginator_mock(
            [[raw_event]] + [[] for _ in range(20)]
        )

        source = AWSIdentitySource(config=AWSConfig(), client=fake_client)
        events = source.fetch_identity_events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actor, "jgarcia")
        self.assertEqual(events[0].source_ip, "203.0.113.5")
        self.assertIn(
            events[0].event_type,
            [IdentityEventType.POLICY_ATTACHED],  # AttachUserPolicy es el primer mapeo
        )

    def test_continues_after_one_event_type_fails(self):
        from botocore.exceptions import ClientError

        fake_client = MagicMock()
        paginator = MagicMock()

        def paginate(**kwargs):
            attr = kwargs["LookupAttributes"][0]["AttributeValue"]
            if attr == "AttachUserPolicy":
                raise ClientError(
                    {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
                    "LookupEvents",
                )
            return iter([{"Events": []}])

        paginator.paginate.side_effect = paginate
        fake_client.get_paginator.return_value = paginator

        source = AWSIdentitySource(config=AWSConfig(), client=fake_client)
        # no debe lanzar excepción — un fallo parcial no tumba la ingesta completa
        events = source.fetch_identity_events()
        self.assertEqual(events, [])

    def test_missing_resource_falls_back_to_actor_as_identity(self):
        fake_client = MagicMock()
        raw_event = {
            "EventTime": datetime(2026, 7, 20, 10, 0, 0),
            "Username": "svc-deploy-bot",
            "Resources": [],
            "CloudTrailEvent": "{}",
        }
        fake_client.get_paginator.return_value = make_paginator_mock(
            [[raw_event]] + [[] for _ in range(20)]
        )

        source = AWSIdentitySource(config=AWSConfig(), client=fake_client)
        events = source.fetch_identity_events()

        self.assertEqual(events[0].identity_id, "svc-deploy-bot")
        self.assertIsNone(events[0].source_ip)


if __name__ == "__main__":
    unittest.main()
