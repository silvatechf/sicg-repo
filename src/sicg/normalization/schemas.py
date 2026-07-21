"""
Modelos de datos normalizados del SICG.

Todo lo que entra por ingestion/ (AWS, Entra ID, GCP en el futuro) se
convierte a estos tipos antes de tocar la capa de correlación. Así el
motor de reglas nunca sabe de dónde vino el dato.

Nota de diseño (ver docs/adr/0001-dataclasses-vs-pydantic.md):
usamos dataclasses de la stdlib en vez de Pydantic para el MVP por
restricciones del entorno de desarrollo. La validación de campos se
hace en __post_init__ para mantener las mismas garantías.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Provider(str, Enum):
    AWS = "aws"
    ENTRA_ID = "entra_id"
    GCP = "gcp"  # placeholder para futuros conectores


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IdentityEventType(str, Enum):
    PRIVILEGE_ESCALATION = "privilege_escalation"
    NEW_ACCESS_KEY = "new_access_key"
    ROLE_ASSUMPTION = "role_assumption"
    POLICY_ATTACHED = "policy_attached"
    MFA_DISABLED = "mfa_disabled"


@dataclass
class IdentityEvent:
    """Evento normalizado de identidad (viene de CloudTrail, Entra audit logs, etc.)."""

    identity_id: str
    provider: Provider
    event_type: IdentityEventType
    timestamp: datetime
    actor: str
    target_permission: Optional[str] = None
    source_ip: Optional[str] = None
    raw: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.identity_id:
            raise ValueError("identity_id no puede estar vacío")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp debe ser datetime")


@dataclass
class CostEvent:
    """Punto de gasto normalizado (viene de Cost Explorer / CUR, Azure Cost Mgmt, etc.)."""

    identity_id: str
    provider: Provider
    service: str  # p.ej. "bedrock", "ec2", "s3"
    amount_usd: float
    timestamp: datetime
    raw: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.amount_usd < 0:
            raise ValueError("amount_usd no puede ser negativo")


@dataclass
class RiskSignal:
    """Salida de la capa de correlación: una señal de riesgo lista para scoring/respuesta."""

    identity_id: str
    severity: Severity
    score: float  # 0.0 - 100.0
    reason: str
    identity_event: Optional[IdentityEvent]
    cost_event: Optional[CostEvent]
    correlated: bool
    detected_at: datetime

    def to_dict(self) -> dict:
        return {
            "identity_id": self.identity_id,
            "severity": self.severity.value,
            "score": round(self.score, 1),
            "reason": self.reason,
            "correlated": self.correlated,
            "detected_at": self.detected_at.isoformat(),
            "identity_event_type": (
                self.identity_event.event_type.value if self.identity_event else None
            ),
            "cost_service": self.cost_event.service if self.cost_event else None,
            "cost_amount_usd": self.cost_event.amount_usd if self.cost_event else None,
        }
