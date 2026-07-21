"""
Capa de respuesta. En el MVP solo notifica (log/consola); el kill switch
automático llega en v1.1 y siempre requiere confirmación explícita o un
umbral de score muy alto + modo "auto_response=True" activado a propósito
(ver roadmap). Nunca se ejecuta una acción destructiva por defecto.
"""

from __future__ import annotations

from sicg.normalization.schemas import RiskSignal, Severity

AUTO_ACTION_THRESHOLD = 90.0  # solo señales CRITICAL muy por encima del umbral


class ConsoleNotifier:
    """Notificador simple para el MVP. Se sustituye por Slack/PagerDuty en v1.0
    implementando la misma interfaz (notify)."""

    def notify(self, signal: RiskSignal) -> str:
        msg = (
            f"[{signal.severity.value.upper()}] score={signal.score:.1f} "
            f"identity={signal.identity_id} — {signal.reason}"
        )
        print(msg)
        return msg


def maybe_recommend_action(signal: RiskSignal, auto_response_enabled: bool = False) -> str | None:
    """Devuelve una recomendación de acción; solo devuelve una acción
    'automática' si auto_response_enabled=True Y se supera el umbral.
    Este flag debe activarse explícitamente por el operador — es el
    guardrail central del roadmap v1.1."""
    if signal.severity != Severity.CRITICAL:
        return None
    if signal.score >= AUTO_ACTION_THRESHOLD and auto_response_enabled:
        return f"ACCIÓN AUTOMÁTICA: revocar credenciales de {signal.identity_id}"
    return f"RECOMENDADO (requiere aprobación humana): revisar y posiblemente revocar {signal.identity_id}"
