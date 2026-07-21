"""
Endpoint de resumen agregado — lo que hoy consume dashboard.html a mano
desde un JSON embebido pasará a pedir esto en vivo.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter

from sicg.api.routers.signals import get_repo

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("")
def summary():
    signals = get_repo().all()
    identities = {s["identity_id"] for s in signals}
    critical = [s for s in signals if s["severity"] == "critical"]

    spend_by_identity = defaultdict(float)
    for s in signals:
        if s.get("cost_amount_usd"):
            spend_by_identity[s["identity_id"]] += s["cost_amount_usd"]

    return {
        "identities_with_signals": len(identities),
        "total_signals": len(signals),
        "critical_signals": len(critical),
        "spend_by_identity": [
            {"identity_id": k, "total_spend": round(v, 2)}
            for k, v in sorted(spend_by_identity.items(), key=lambda x: -x[1])
        ],
    }
