"""
Conector real de eventos de identidad en Entra ID (antes Azure AD) vía
Microsoft Graph API.

Auth: client credentials flow con msal (la librería oficial de Microsoft
para MSAL — la forma correcta de autenticar una app/servicio sin usuario
interactivo). El token se cachea internamente por msal.

Datos: /auditLogs/directoryAudits, filtrado a categorías sensibles
(RoleManagement, UserManagement con actividades de MFA).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import msal
import requests

from sicg.config import EntraConfig
from sicg.normalization.schemas import IdentityEvent, IdentityEventType, Provider

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]

# Mapeo de activityDisplayName de Entra a nuestro tipo normalizado.
SENSITIVE_ACTIVITIES: dict[str, IdentityEventType] = {
    "Add member to role": IdentityEventType.PRIVILEGE_ESCALATION,
    "Add eligible member to role": IdentityEventType.PRIVILEGE_ESCALATION,
    "Update role definition": IdentityEventType.PRIVILEGE_ESCALATION,
    "Disable Strong Authentication": IdentityEventType.MFA_DISABLED,
    "Add app role assignment to service principal": IdentityEventType.POLICY_ATTACHED,
    "Add service principal credentials": IdentityEventType.NEW_ACCESS_KEY,
}


class EntraIdentitySource:
    """Implementa la interfaz IdentitySource (ingestion/base.py) contra Microsoft Graph real."""

    def __init__(self, config: EntraConfig | None = None, session: requests.Session | None = None):
        self.config = config or EntraConfig()
        self._session = session or requests.Session()
        self._app: msal.ConfidentialClientApplication | None = None

    def _get_app(self) -> msal.ConfidentialClientApplication:
        if self._app is None:
            self.config.validate()
            self._app = msal.ConfidentialClientApplication(
                client_id=self.config.client_id,
                client_credential=self.config.client_secret,
                authority=f"https://login.microsoftonline.com/{self.config.tenant_id}",
            )
        return self._app

    def _get_token(self) -> str:
        app = self._get_app()
        result = app.acquire_token_silent(GRAPH_SCOPE, account=None)
        if not result:
            result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
        if "access_token" not in result:
            raise RuntimeError(
                f"No se pudo obtener token de Microsoft Graph: "
                f"{result.get('error_description', result.get('error', 'error desconocido'))}"
            )
        return result["access_token"]

    def fetch_identity_events(self) -> list[IdentityEvent]:
        token = self._get_token()
        since = (datetime.utcnow() - timedelta(days=self.config.lookback_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        url = (
            f"{GRAPH_BASE_URL}/auditLogs/directoryAudits"
            f"?$filter=activityDateTime ge {since}&$top=100"
        )
        headers = {"Authorization": f"Bearer {token}"}

        events: list[IdentityEvent] = []
        while url:
            resp = self._session.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                logger.error(
                    "Fallo al consultar Microsoft Graph (%s): %s", resp.status_code, resp.text
                )
                resp.raise_for_status()

            payload = resp.json()
            for raw_event in payload.get("value", []):
                parsed = self._parse_event(raw_event)
                if parsed:
                    events.append(parsed)

            url = payload.get("@odata.nextLink")  # paginación estándar de Graph

        return events

    def _parse_event(self, raw_event: dict) -> IdentityEvent | None:
        activity = raw_event.get("activityDisplayName", "")
        event_type = SENSITIVE_ACTIVITIES.get(activity)
        if event_type is None:
            return None  # actividad no relevante para SICG, se descarta

        target_resources = raw_event.get("targetResources", [])
        identity_id = target_resources[0].get("id", "unknown") if target_resources else "unknown"

        initiator = raw_event.get("initiatedBy", {}).get("user", {})
        actor = initiator.get("userPrincipalName", "unknown")

        timestamp_str = raw_event.get("activityDateTime")
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str
            else datetime.utcnow()
        )

        return IdentityEvent(
            identity_id=identity_id,
            provider=Provider.ENTRA_ID,
            event_type=event_type,
            timestamp=timestamp,
            actor=actor,
            source_ip=raw_event.get("initiatedBy", {}).get("user", {}).get("ipAddress"),
            raw=raw_event,
        )
