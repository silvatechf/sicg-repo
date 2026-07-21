import unittest
from datetime import datetime, timedelta

from sicg.correlation.rules_engine import correlate, find_cost_spikes
from sicg.normalization.schemas import (
    CostEvent,
    IdentityEvent,
    IdentityEventType,
    Provider,
)

NOW = datetime(2026, 7, 20, 12, 0, 0)


def cost(identity, amount, hours_ago, service="ec2"):
    return CostEvent(
        identity_id=identity,
        provider=Provider.AWS,
        service=service,
        amount_usd=amount,
        timestamp=NOW - timedelta(hours=hours_ago),
    )


def id_event(identity, event_type, hours_ago, source_ip="10.0.0.5"):
    return IdentityEvent(
        identity_id=identity,
        provider=Provider.AWS,
        event_type=event_type,
        timestamp=NOW - timedelta(hours=hours_ago),
        actor=identity,
        source_ip=source_ip,
    )


class TestFindCostSpikes(unittest.TestCase):
    def test_detects_spike_above_baseline(self):
        events = [cost("user-a", 10, h) for h in range(1, 10)] + [cost("user-a", 500, 0)]
        spikes = find_cost_spikes(events)
        self.assertEqual(len(spikes), 1)
        self.assertEqual(spikes[0].amount_usd, 500)

    def test_no_spike_when_amounts_stable(self):
        events = [cost("user-a", 10 + i * 0.1, h) for i, h in enumerate(range(1, 10))]
        spikes = find_cost_spikes(events)
        self.assertEqual(len(spikes), 0)

    def test_single_event_never_a_spike(self):
        events = [cost("user-a", 999, 0)]
        spikes = find_cost_spikes(events)
        self.assertEqual(len(spikes), 0)


class TestCorrelate(unittest.TestCase):
    def test_correlates_sensitive_event_with_nearby_spike(self):
        costs = [cost("user-a", 10, h) for h in range(2, 10)] + [
            cost("user-a", 800, 0.5, service="bedrock")
        ]
        identities = [id_event("user-a", IdentityEventType.PRIVILEGE_ESCALATION, 0.6)]

        signals = correlate(identities, costs, now=NOW)

        correlated = [s for s in signals if s.correlated]
        self.assertEqual(len(correlated), 1)
        self.assertEqual(correlated[0].identity_id, "user-a")
        self.assertTrue(correlated[0].correlated)

    def test_spike_outside_window_not_correlated(self):
        costs = [cost("user-a", 10, h) for h in range(2, 10)] + [
            cost("user-a", 800, 0.1, service="bedrock")
        ]
        # evento sensible 5 horas antes del pico -> fuera de la ventana de 2h
        identities = [id_event("user-a", IdentityEventType.PRIVILEGE_ESCALATION, 5)]

        signals = correlate(identities, costs, now=NOW)

        self.assertTrue(all(not s.correlated for s in signals))
        self.assertEqual(len(signals), 1)  # el pico se reporta igual, sin correlación

    def test_no_signals_when_no_spikes_or_events(self):
        costs = [cost("user-a", 10, h) for h in range(1, 10)]
        signals = correlate([], costs, now=NOW)
        self.assertEqual(len(signals), 0)


if __name__ == "__main__":
    unittest.main()
