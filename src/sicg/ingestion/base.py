"""
Interfaz que deben cumplir todos los conectores de ingestión.

Los conectores reales (aws_cost.py, aws_iam.py, entra_id.py) implementarán
estos Protocols cuando haya credenciales/red disponibles. synthetic.py
los cumple hoy con datos generados para poder desarrollar y testear
correlation/ y response/ sin depender de infraestructura real.
"""

from __future__ import annotations

from typing import Protocol

from sicg.normalization.schemas import CostEvent, IdentityEvent


class CostSource(Protocol):
    def fetch_cost_events(self) -> list[CostEvent]: ...


class IdentitySource(Protocol):
    def fetch_identity_events(self) -> list[IdentityEvent]: ...
