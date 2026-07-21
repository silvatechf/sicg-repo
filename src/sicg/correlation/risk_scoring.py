"""
Scoring ponderado de las señales que salen del rules_engine.

Heurístico y explicable a propósito (ver ADR 0002): cada factor suma
puntos con un peso fijo. Es fácil de auditar ("¿por qué 87 puntos?")
y fácil de recalibrar cuando haya datos reales de producción.
"""

from __future__ import annotations

from sicg.normalization.schemas import IdentityEventType, RiskSignal, Severity

WEIGHTS = {
    "correlated_base": 50.0,          # evento sensible + pico de gasto en ventana
    "uncorrelated_base": 15.0,        # solo pico de gasto
    "privilege_escalation": 25.0,     # el tipo de evento más grave
    "mfa_disabled": 20.0,
    "new_access_key": 10.0,
    "policy_attached": 10.0,
    "unusual_source_ip": 10.0,        # heurística simple: IP fuera de rango conocido "10.0.x.x"
    "high_amount": 15.0,              # gasto > $500 en un solo evento
}

_EVENT_WEIGHT_KEY = {
    IdentityEventType.PRIVILEGE_ESCALATION: "privilege_escalation",
    IdentityEventType.MFA_DISABLED: "mfa_disabled",
    IdentityEventType.NEW_ACCESS_KEY: "new_access_key",
    IdentityEventType.POLICY_ATTACHED: "policy_attached",
}


def _severity_from_score(score: float) -> Severity:
    if score >= 80:
        return Severity.CRITICAL
    if score >= 50:
        return Severity.HIGH
    if score >= 25:
        return Severity.MEDIUM
    return Severity.LOW


def score(signal: RiskSignal) -> RiskSignal:
    """Calcula el score final de una señal y ajusta su severidad. Devuelve
    una nueva instancia (no muta la de entrada) para mantener el pipeline
    fácil de testear paso a paso."""
    total = WEIGHTS["correlated_base"] if signal.correlated else WEIGHTS["uncorrelated_base"]

    if signal.identity_event is not None:
        key = _EVENT_WEIGHT_KEY.get(signal.identity_event.event_type)
        if key:
            total += WEIGHTS[key]
        if signal.identity_event.source_ip and not signal.identity_event.source_ip.startswith(
            "10.0."
        ):
            total += WEIGHTS["unusual_source_ip"]

    if signal.cost_event is not None and signal.cost_event.amount_usd > 500:
        total += WEIGHTS["high_amount"]

    total = min(total, 100.0)

    return RiskSignal(
        identity_id=signal.identity_id,
        severity=_severity_from_score(total),
        score=total,
        reason=signal.reason,
        identity_event=signal.identity_event,
        cost_event=signal.cost_event,
        correlated=signal.correlated,
        detected_at=signal.detected_at,
    )


def score_all(signals: list[RiskSignal]) -> list[RiskSignal]:
    return sorted((score(s) for s in signals), key=lambda s: s.score, reverse=True)
