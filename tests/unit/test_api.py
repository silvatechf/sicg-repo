"""
Tests de la API con TestClient (in-process, sin levantar un servidor real
— es la forma correcta de testear endpoints de FastAPI).
"""

import unittest
from datetime import datetime

from fastapi.testclient import TestClient

from sicg.api.main import app
from sicg.api.routers.signals import set_repo
from sicg.normalization.schemas import RiskSignal, Severity
from sicg.storage.repository import SignalRepository


def seed_repo():
    repo = SignalRepository()
    repo.save_all(
        [
            RiskSignal(
                identity_id="arn:aws:iam::111:user/a",
                severity=Severity.CRITICAL,
                score=95.0,
                reason="test critical",
                identity_event=None,
                cost_event=None,
                correlated=True,
                detected_at=datetime(2026, 7, 20, 12, 0, 0),
            ),
            RiskSignal(
                identity_id="arn:aws:iam::111:user/b",
                severity=Severity.MEDIUM,
                score=30.0,
                reason="test medium",
                identity_event=None,
                cost_event=None,
                correlated=False,
                detected_at=datetime(2026, 7, 20, 12, 0, 0),
            ),
        ]
    )
    set_repo(repo)


class TestAPI(unittest.TestCase):
    def setUp(self):
        seed_repo()
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_list_signals(self):
        resp = self.client.get("/signals")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 2)

    def test_filter_by_severity(self):
        resp = self.client.get("/signals", params={"severity": "critical"})
        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["signals"][0]["identity_id"], "arn:aws:iam::111:user/a")

    def test_filter_by_min_score(self):
        resp = self.client.get("/signals", params={"min_score": 90})
        self.assertEqual(resp.json()["count"], 1)

    def test_get_signals_for_identity(self):
        resp = self.client.get("/signals/arn:aws:iam::111:user/a")
        self.assertEqual(resp.json()["count"], 1)

    def test_get_signals_for_unknown_identity(self):
        resp = self.client.get("/signals/does-not-exist")
        self.assertEqual(resp.json()["count"], 0)

    def test_summary(self):
        resp = self.client.get("/summary")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total_signals"], 2)
        self.assertEqual(resp.json()["critical_signals"], 1)

    def test_run_pipeline_endpoint(self):
        resp = self.client.post("/pipeline/run")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")
        self.assertGreaterEqual(resp.json()["signals_generated"], 0)


if __name__ == "__main__":
    unittest.main()
