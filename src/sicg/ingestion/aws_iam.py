"""
Conector real de eventos de identidad AWS vía CloudTrail.

Usa lookup_events (API síncrona simple, sin infraestructura adicional) en
vez de CloudTrail Lake/Athena. Correcto para el volumen de un MVP; si el
trail crece mucho, la migración natural es a Athena sobre S3 (mismo
CostSource/IdentitySource, solo cambia la query interna).

lookup_events solo permite un LookupAttribute a la vez, así que hacemos
una llamada por cada nombre de evento sensible y las combinamos — es la
forma correcta de usar esta API para varios EventName distintos.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from sicg.config import AWSConfig
from sicg.normalization.schemas import IdentityEvent, IdentityEventType, Provider

logger = logging.getLogger(__name__)

# Mapeo de nombres de evento de CloudTrail a nuestro tipo normalizado.
# Esta lista es el "diccionario de sensibilidad" del sistema — ampliarla
# es la forma principal de mejorar la cobertura de detección.
SENSITIVE_EVENT_NAMES: dict[str, IdentityEventType] = {
    "AttachUserPolicy": IdentityEventType.POLICY_ATTACHED,
    "AttachRolePolicy": IdentityEventType.POLICY_ATTACHED,
    "PutUserPolicy": IdentityEventType.POLICY_ATTACHED,
    "CreateAccessKey": IdentityEventType.NEW_ACCESS_KEY,
    "AssumeRole": IdentityEventType.ROLE_ASSUMPTION,
    "DeactivateMFADevice": IdentityEventType.MFA_DISABLED,
    "DeleteVirtualMFADevice": IdentityEventType.MFA_DISABLED,
    "UpdateAssumeRolePolicy": IdentityEventType.PRIVILEGE_ESCALATION,
    "CreatePolicyVersion": IdentityEventType.PRIVILEGE_ESCALATION,
    "AttachGroupPolicy": IdentityEventType.PRIVILEGE_ESCALATION,
}


class AWSIdentitySource:
    """Implementa la interfaz IdentitySource (ingestion/base.py) contra CloudTrail real."""

    def __init__(self, config: AWSConfig | None = None, client=None):
        self.config = config or AWSConfig()
        self._client = client or boto3.client("cloudtrail", region_name=self.config.region)

    def fetch_identity_events(self) -> list[IdentityEvent]:
        end = datetime.utcnow()
        start = end - timedelta(days=self.config.lookback_days)

        events: list[IdentityEvent] = []
        for event_name, event_type in SENSITIVE_EVENT_NAMES.items():
            try:
                events.extend(
                    self._lookup_one_event_type(event_name, event_type, start, end)
                )
            except (BotoCoreError, ClientError) as exc:
                # Un fallo en un tipo de evento no debe tumbar la ingesta completa
                # de los demás — se loguea y se continúa.
                logger.error("Fallo al consultar CloudTrail para %s: %s", event_name, exc)

        return events

    def _lookup_one_event_type(
        self, event_name: str, event_type: IdentityEventType, start: datetime, end: datetime
    ) -> list[IdentityEvent]:
        results = []
        paginator = self._client.get_paginator("lookup_events")
        pages = paginator.paginate(
            LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": event_name}],
            StartTime=start,
            EndTime=end,
        )
        for page in pages:
            for raw_event in page.get("Events", []):
                results.append(self._parse_event(raw_event, event_type))
        return results

    def _parse_event(self, raw_event: dict, event_type: IdentityEventType) -> IdentityEvent:
        actor = raw_event.get("Username", "unknown")
        resources = raw_event.get("Resources", [])
        identity_id = resources[0]["ResourceName"] if resources else actor

        source_ip = None
        cloudtrail_event = raw_event.get("CloudTrailEvent", "")
        # CloudTrailEvent es un JSON-string; solo extraemos sourceIPAddress
        # sin necesidad de parsear todo el documento.
        if '"sourceIPAddress":"' in cloudtrail_event:
            try:
                source_ip = cloudtrail_event.split('"sourceIPAddress":"')[1].split('"')[0]
            except IndexError:
                source_ip = None

        return IdentityEvent(
            identity_id=identity_id,
            provider=Provider.AWS,
            event_type=event_type,
            timestamp=raw_event["EventTime"],
            actor=actor,
            source_ip=source_ip,
            raw=raw_event,
        )
