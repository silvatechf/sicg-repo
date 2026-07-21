import os
import unittest
from unittest.mock import MagicMock, patch

from sicg.config import EntraConfig
from sicg.ingestion.entra_id import EntraIdentitySource
from sicg.normalization.schemas import IdentityEventType, Provider


def make_config():
    return EntraConfig(
        tenant_id="tenant-123",
        client_id="client-abc",
        client_secret="secret-xyz",
    )


class TestEntraIdentitySource(unittest.TestCase):
    @patch("sicg.ingestion.entra_id.msal.ConfidentialClientApplication")
    def test_parses_sensitive_activity(self, mock_msal_app_cls):
        mock_app = MagicMock()
        mock_app.acquire_token_silent.return_value = None
        mock_app.acquire_token_for_client.return_value = {"access_token": "fake-token"}
        mock_msal_app_cls.return_value = mock_app

        fake_session = MagicMock()
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "value": [
                {
                    "activityDisplayName": "Add member to role",
                    "activityDateTime": "2026-07-20T10:00:00Z",
                    "targetResources": [{"id": "user-object-id-123"}],
                    "initiatedBy": {
                        "user": {
                            "userPrincipalName": "admin@empresa.com",
                            "ipAddress": "198.51.100.1",
                        }
                    },
                },
                {
                    # actividad no sensible -> debe descartarse
                    "activityDisplayName": "User read profile",
                    "activityDateTime": "2026-07-20T09:00:00Z",
                    "targetResources": [{"id": "irrelevant"}],
                    "initiatedBy": {"user": {"userPrincipalName": "someone@empresa.com"}},
                },
            ]
            # sin @odata.nextLink -> una sola página
        }
        fake_session.get.return_value = fake_response

        source = EntraIdentitySource(config=make_config(), session=fake_session)
        events = source.fetch_identity_events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, IdentityEventType.PRIVILEGE_ESCALATION)
        self.assertEqual(events[0].provider, Provider.ENTRA_ID)
        self.assertEqual(events[0].actor, "admin@empresa.com")
        self.assertEqual(events[0].identity_id, "user-object-id-123")

    @patch("sicg.ingestion.entra_id.msal.ConfidentialClientApplication")
    def test_follows_pagination(self, mock_msal_app_cls):
        mock_app = MagicMock()
        mock_app.acquire_token_silent.return_value = None
        mock_app.acquire_token_for_client.return_value = {"access_token": "fake-token"}
        mock_msal_app_cls.return_value = mock_app

        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "value": [],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page",
        }
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {"value": []}

        fake_session = MagicMock()
        fake_session.get.side_effect = [page1, page2]

        source = EntraIdentitySource(config=make_config(), session=fake_session)
        source.fetch_identity_events()

        self.assertEqual(fake_session.get.call_count, 2)

    def test_raises_clear_error_when_config_incomplete(self):
        source = EntraIdentitySource(config=EntraConfig(tenant_id="", client_id="", client_secret=""))
        with self.assertRaises(Exception):
            source._get_app()


if __name__ == "__main__":
    unittest.main()
