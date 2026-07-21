"""
Motor de correlación basado en reglas explicables.

Deliberadamente NO usamos ML aquí en el MVP (ver docs/adr/0002-reglas-antes-que-ml.md).
Un sistema de seguridad que dispara kill switches tiene que poder explicar,
en una frase, por qué se disparó. Las reglas son ese contrato.

Regla principal: si una identidad tiene un evento de escalada de
privilegios / cambio sensible (nueva key, MFA off, nuevo permiso) y,
dentro de una ventana de tiempo corta, un pico de gasto muy por encima
de su baseline histórico -> señal de riesgo correlacionada.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from sicg.normalization.schemas import (
    CostEvent,
    IdentityEvent,
    IdentityEventType,
    RiskSignal,
    Severity,
)

# Tipos de evento de identidad que consideramos "sensibles" a efectos de correlación
SENSITIVE_EVENT_TYPES = {
    IdentityEventType.PRIVILEGE_ESCALATION,
    IdentityEventType.MFA_DISABLED,
    IdentityEventType.POLICY_ATTACHED,
    IdentityEventType.NEW_ACCESS_KEY,
}

CORRELATION_WINDOW = timedelta(hours=2)
SPIKE_STDDEV_MULTIPLIER = 3.0  # cuántas desviaciones estándar sobre la media cuenta como "pico"


def _baseline_stats(amounts: list[float]) -> tuple[float, float]:
    if len(amounts) < 2:
        return (amounts[0] if amounts else 0.0, 0.0)
    return statistics.mean(amounts), statistics.pstdev(amounts)


def _is_spike(amount: float, mean: float, stddev: float) -> bool:
    if stddev == 0:
        return amount > mean * 3 and mean > 0
    return amount > mean + SPIKE_STDDEV_MULTIPLIER * stddev


def find_cost_spikes(cost_events: list[CostEvent]) -> list[CostEvent]:
    """Identifica eventos de coste que son anómalos respecto al baseline de esa identidad.

    El baseline de cada evento se calcula EXCLUYENDO el propio evento —
    si no, un pico grande se cuela en su propia media y se auto-enmascara
    (un solo outlier infla tanto la media como la desviación estándar)."""
    by_identity: dict[str, list[CostEvent]] = {}
    for e in cost_events:
        by_identity.setdefault(e.identity_id, []).append(e)

    spikes = []
    for identity_id, events in by_identity.items():
        for i, e in enumerate(events):
            others = [ev.amount_usd for j, ev in enumerate(events) if j != i]
            mean, stddev = _baseline_stats(others)
            if _is_spike(e.amount_usd, mean, stddev):
                spikes.append(e)
    return spikes


def correlate(
    identity_events: list[IdentityEvent],
    cost_events: list[CostEvent],
    now: datetime | None = None,
) -> list[RiskSignal]:
    """Regla principal de correlación. Devuelve una señal por cada
    combinación (evento sensible, pico de gasto) que caiga dentro de
    la ventana de correlación para la misma identidad."""
    now = now or datetime.utcnow()
    signals: list[RiskSignal] = []

    spikes = find_cost_spikes(cost_events)
    sensitive_events = [e for e in identity_events if e.event_type in SENSITIVE_EVENT_TYPES]

    matched_spike_ids = set()

    for id_event in sensitive_events:
        for spike in spikes:
            if spike.identity_id != id_event.identity_id:
                continue
            delta = abs((spike.timestamp - id_event.timestamp).total_seconds())
            if delta <= CORRELATION_WINDOW.total_seconds():
                signals.append(
                    RiskSignal(
                        identity_id=id_event.identity_id,
                        severity=Severity.CRITICAL,
                        score=0.0,  # se rellena en risk_scoring.score()
                        reason=(
                            f"Evento sensible '{id_event.event_type.value}' seguido de pico de "
                            f"gasto en '{spike.service}' (${spike.amount_usd:.2f}) "
                            f"{int(delta // 60)} min después"
                        ),
                        identity_event=id_event,
                        cost_event=spike,
                        correlated=True,
                        detected_at=now,
                    )
                )
                matched_spike_ids.add(id(spike))

    # Picos de gasto sin evento sensible asociado: riesgo más bajo,
    # pero igualmente reportable (podría ser un uso legítimo intensivo).
    for spike in spikes:
        if id(spike) in matched_spike_ids:
            continue
        signals.append(
            RiskSignal(
                identity_id=spike.identity_id,
                severity=Severity.MEDIUM,
                score=0.0,
                reason=(
                    f"Pico de gasto no correlacionado en '{spike.service}' "
                    f"(${spike.amount_usd:.2f}), sin evento de identidad sensible cercano"
                ),
                identity_event=None,
                cost_event=spike,
                correlated=False,
                detected_at=now,
            )
        )

    return signals
