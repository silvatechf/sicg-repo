import unittest
from datetime import datetime

from sicg.correlation.risk_scoring import score, score_all
from sicg.normalization.schemas import (
    CostEvent,
    IdentityEvent,
    IdentityEventType,
    Provider,
    RiskSignal,
    Severity,
)

NOW = datetime(2026, 7, 20, 12, 0, 0)


def make_signal(correlated, event_type=None, amount=100.0, source_ip="10.0.0.5"):
    id_evt = None
    if event_type:
        id_evt = IdentityEvent(
            identity_id="user-a",
            provider=Provider.AWS,
            event_type=event_type,
            timestamp=NOW,
            actor="user-a",
            source_ip=source_ip,
        )
    cost_evt = CostEvent(
        identity_id="user-a",
        provider=Provider.AWS,
        service="ec2",
        amount_usd=amount,
        timestamp=NOW,
    )
    return RiskSignal(
        identity_id="user-a",
        severity=Severity.LOW,
        score=0.0,
        reason="test",
        identity_event=id_evt,
        cost_event=cost_evt,
        correlated=correlated,
        detected_at=NOW,
    )


class TestRiskScoring(unittest.TestCase):
    def test_correlated_scores_higher_than_uncorrelated(self):
        correlated = score(make_signal(True, IdentityEventType.PRIVILEGE_ESCALATION))
        uncorrelated = score(make_signal(False))
        self.assertGreater(correlated.score, uncorrelated.score)

    def test_privilege_escalation_plus_unusual_ip_plus_high_amount_is_critical(self):
        signal = make_signal(
            True,
            IdentityEventType.PRIVILEGE_ESCALATION,
            amount=1000.0,
            source_ip="203.0.113.5",
        )
        result = score(signal)
        self.assertEqual(result.severity, Severity.CRITICAL)
        self.assertGreaterEqual(result.score, 80)

    def test_score_never_exceeds_100(self):
        signal = make_signal(
            True, IdentityEventType.PRIVILEGE_ESCALATION, amount=99999.0, source_ip="1.2.3.4"
        )
        result = score(signal)
        self.assertLessEqual(result.score, 100.0)

    def test_score_all_sorts_descending(self):
        signals = [
            make_signal(False),
            make_signal(True, IdentityEventType.PRIVILEGE_ESCALATION),
            make_signal(True, IdentityEventType.NEW_ACCESS_KEY),
        ]
        results = score_all(signals)
        scores = [r.score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_does_not_mutate_input_signal(self):
        original = make_signal(True, IdentityEventType.PRIVILEGE_ESCALATION)
        score(original)
        self.assertEqual(original.score, 0.0)  # el original no cambió


if __name__ == "__main__":
    unittest.main()
