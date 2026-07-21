"""
Configuración de los conectores reales. Todo por variables de entorno —
nunca credenciales hardcodeadas ni en el repo.

AWS: usa la cadena de credenciales estándar de boto3 (env vars, perfil de
~/.aws/credentials, o rol de IAM si corre en EC2/Lambda/ECS). No pedimos
access key/secret aquí a propósito; dejar que boto3 resuelva credenciales
es la práctica correcta y evita que alguien las pase mal por env vars.

Entra ID: requiere client credentials flow (app registration), sí necesita
tenant_id / client_id / client_secret explícitos porque no hay equivalente
al rol de IAM de AWS para procesos batch fuera de Azure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Falta configuración requerida para un conector."""


@dataclass(frozen=True)
class AWSConfig:
    region: str = os.environ.get("SICG_AWS_REGION", "eu-west-1")
    # Ventana de lookback para CloudTrail / Cost Explorer
    lookback_days: int = int(os.environ.get("SICG_LOOKBACK_DAYS", "14"))
    # Cost allocation tag usada para atribuir gasto a una identidad IAM.
    # "aws:createdBy" es la tag automática que AWS ofrece desde 2022 para
    # esto exactamente — hay que activarla en Billing > Cost allocation tags.
    cost_allocation_tag: str = os.environ.get("SICG_COST_TAG", "aws:createdBy")


@dataclass(frozen=True)
class EntraConfig:
    tenant_id: str = os.environ.get("SICG_ENTRA_TENANT_ID", "")
    client_id: str = os.environ.get("SICG_ENTRA_CLIENT_ID", "")
    client_secret: str = os.environ.get("SICG_ENTRA_CLIENT_SECRET", "")
    lookback_days: int = int(os.environ.get("SICG_LOOKBACK_DAYS", "14"))

    def validate(self) -> None:
        missing = [
            name
            for name, val in [
                ("SICG_ENTRA_TENANT_ID", self.tenant_id),
                ("SICG_ENTRA_CLIENT_ID", self.client_id),
                ("SICG_ENTRA_CLIENT_SECRET", self.client_secret),
            ]
            if not val
        ]
        if missing:
            raise ConfigError(
                f"Faltan variables de entorno para el conector de Entra ID: {', '.join(missing)}"
            )
