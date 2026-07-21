"""
Orquesta el pipeline completo: ingestión -> correlación -> scoring -> respuesta -> storage.

Uso:
    python -m sicg.pipeline
"""

from __future__ import annotations

from sicg.correlation.risk_scoring import score_all
from sicg.correlation.rules_engine import correlate
from sicg.ingestion.synthetic import generate_cost_events, generate_identity_events
from sicg.response.notifiers import ConsoleNotifier, maybe_recommend_action
from sicg.storage.repository import SignalRepository


def run_pipeline(export_path: str | None = None) -> list[dict]:
    cost_events = generate_cost_events()
    identity_events = generate_identity_events()

    raw_signals = correlate(identity_events, cost_events)
    scored_signals = score_all(raw_signals)

    notifier = ConsoleNotifier()
    for signal in scored_signals:
        notifier.notify(signal)
        action = maybe_recommend_action(signal)
        if action:
            print(f"  -> {action}")

    repo = SignalRepository()
    repo.save_all(scored_signals)

    if export_path:
        repo.export_json(export_path)

    return repo.all()


if __name__ == "__main__":
    run_pipeline(export_path="dashboard_data.json")
