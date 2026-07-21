"""
Conector real de AWS Cost Explorer.

Implementa CostSource (ver base.py) con la misma forma que synthetic.py,
para que rules_engine.py no note ninguna diferencia.

Atribución de gasto a identidad IAM: Cost Explorer no tiene una dimensión
nativa "IAM user/role". El enfoque correcto es agrupar por la cost
allocation tag "aws:createdBy" (tag automática de AWS desde 2022, hay que
activarla una vez en Billing > Cost allocation tags) — captura el ARN de
quien creó cada recurso, así que el gasto de ese recurso se atribuye a esa
identidad de forma nativa, sin tener que taggear nada a mano.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from sicg.config import AWSConfig
from sicg.normalization.schemas import CostEvent, Provider

logger = logging.getLogger(__name__)


class AWSCostSource:
    """Implementa la interfaz CostSource (ingestion/base.py) contra la API real."""

    def __init__(self, config: AWSConfig | None = None, client=None):
        self.config = config or AWSConfig()
        # Permite inyectar un cliente boto3 ya creado — imprescindible para
        # poder testear esta clase con un cliente mockeado, sin credenciales.
        self._client = client or boto3.client("ce", region_name=self.config.region)

    def fetch_cost_events(self) -> list[CostEvent]:
        end = datetime.utcnow().date()
        start = end - timedelta(days=self.config.lookback_days)

        try:
            response = self._client.get_cost_and_usage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
                GroupBy=[
                    {"Type": "TAG", "Key": self.config.cost_allocation_tag},
                    {"Type": "DIMENSION", "Key": "SERVICE"},
                ],
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("Fallo al consultar Cost Explorer: %s", exc)
            raise

        return self._parse_response(response)

    def _parse_response(self, response: dict) -> list[CostEvent]:
        events: list[CostEvent] = []
        for day_result in response.get("ResultsByTime", []):
            ts = datetime.fromisoformat(day_result["TimePeriod"]["Start"])
            for group in day_result.get("Groups", []):
                keys = group.get("Keys", [])
                identity_tag_value = keys[0] if keys else "untagged"
                service = keys[1] if len(keys) > 1 else "unknown"
                amount = float(
                    group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0.0)
                )
                if amount <= 0:
                    continue

                # el valor de la tag viene como "aws:createdBy$AWSAssumedRole$..."
                # o directamente el ARN; normalizamos quedándonos con la parte
                # útil si trae el prefijo de la tag.
                identity_id = identity_tag_value.split("$")[-1] or "untagged"

                events.append(
                    CostEvent(
                        identity_id=identity_id,
                        provider=Provider.AWS,
                        service=service.lower(),
                        amount_usd=round(amount, 2),
                        timestamp=ts,
                        raw=group,
                    )
                )
        return events
