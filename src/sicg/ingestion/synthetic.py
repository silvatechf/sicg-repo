"""
Generador de datos sintéticos para desarrollo local sin credenciales reales.

Implementa la misma interfaz que tendrán aws_cost.py / aws_iam.py
(ver base.py) para que el resto del pipeline no note la diferencia
cuando se conecten los conectores reales.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from sicg.normalization.schemas import CostEvent, IdentityEvent, IdentityEventType, Provider

IDENTITIES = [
    "arn:aws:iam::111122223333:user/jgarcia",
    "arn:aws:iam::111122223333:user/svc-deploy-bot",
    "arn:aws:iam::111122223333:role/lambda-etl-role",
    "arn:aws:iam::111122223333:user/mrodriguez",
    "arn:aws:iam::111122223333:user/analytics-readonly",
]

SERVICES = ["bedrock", "ec2", "s3", "sagemaker", "rds", "lambda"]


def generate_cost_events(n: int = 200, seed: int = 42) -> list[CostEvent]:
    """Genera una serie de gasto diario 'normal' con un par de picos anómalos inyectados."""
    rng = random.Random(seed)
    events: list[CostEvent] = []
    now = datetime.utcnow()

    for identity in IDENTITIES:
        base_daily = rng.uniform(5, 40)
        for day in range(n // len(IDENTITIES)):
            ts = now - timedelta(days=(n // len(IDENTITIES)) - day)
            amount = max(0.0, rng.gauss(base_daily, base_daily * 0.15))
            events.append(
                CostEvent(
                    identity_id=identity,
                    provider=Provider.AWS,
                    service=rng.choice(SERVICES),
                    amount_usd=round(amount, 2),
                    timestamp=ts,
                )
            )

    # Picos anómalos inyectados a propósito, correlacionados en el tiempo
    # con eventos de escalada de privilegios que añadimos abajo.
    spike_identity = "arn:aws:iam::111122223333:user/analytics-readonly"
    spike_time = now - timedelta(hours=6)
    events.append(
        CostEvent(
            identity_id=spike_identity,
            provider=Provider.AWS,
            service="bedrock",
            amount_usd=1840.55,
            timestamp=spike_time,
        )
    )

    spike_identity_2 = "arn:aws:iam::111122223333:user/svc-deploy-bot"
    spike_time_2 = now - timedelta(hours=30)
    events.append(
        CostEvent(
            identity_id=spike_identity_2,
            provider=Provider.AWS,
            service="ec2",
            amount_usd=620.10,
            timestamp=spike_time_2,
        )
    )

    return events


def generate_identity_events(seed: int = 42) -> list[IdentityEvent]:
    """Genera eventos de identidad, incluyendo 2 escaladas de privilegios
    temporalmente cercanas a los picos de gasto (para que el motor de
    correlación tenga algo real que encontrar)."""
    rng = random.Random(seed)
    now = datetime.utcnow()
    events: list[IdentityEvent] = []

    # Ruido de fondo: eventos normales, sin correlación con gasto
    for identity in IDENTITIES:
        for _ in range(rng.randint(1, 3)):
            ts = now - timedelta(days=rng.randint(2, 20), hours=rng.randint(0, 23))
            events.append(
                IdentityEvent(
                    identity_id=identity,
                    provider=Provider.AWS,
                    event_type=rng.choice(
                        [IdentityEventType.ROLE_ASSUMPTION, IdentityEventType.NEW_ACCESS_KEY]
                    ),
                    timestamp=ts,
                    actor=identity,
                    source_ip=f"10.0.{rng.randint(0,255)}.{rng.randint(0,255)}",
                )
            )

    # Señal 1: escalada de privilegios ~40 min antes del pico de gasto en Bedrock
    events.append(
        IdentityEvent(
            identity_id="arn:aws:iam::111122223333:user/analytics-readonly",
            provider=Provider.AWS,
            event_type=IdentityEventType.PRIVILEGE_ESCALATION,
            timestamp=now - timedelta(hours=6, minutes=40),
            actor="arn:aws:iam::111122223333:user/analytics-readonly",
            target_permission="bedrock:InvokeModel",
            source_ip="203.0.113.77",  # IP fuera de los rangos habituales
        )
    )

    # Señal 2: nueva access key + MFA deshabilitado justo antes del pico en EC2
    events.append(
        IdentityEvent(
            identity_id="arn:aws:iam::111122223333:user/svc-deploy-bot",
            provider=Provider.AWS,
            event_type=IdentityEventType.MFA_DISABLED,
            timestamp=now - timedelta(hours=30, minutes=15),
            actor="arn:aws:iam::111122223333:user/svc-deploy-bot",
            source_ip="198.51.100.23",
        )
    )

    return events
