"""
API del SICG. Sirve los datos que hoy el dashboard.html lee de un JSON
embebido a mano, y deja la puerta abierta a exponerlo a otras
herramientas (Slack bot, CLI, etc.) sin duplicar lógica.

Correr en local:
    uvicorn sicg.api.main:app --reload

Correr el pipeline y dejar sus resultados disponibles vía API:
    POST /pipeline/run
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sicg.api.routers import signals, summary
from sicg.api.routers.signals import set_repo
from sicg.correlation.risk_scoring import score_all
from sicg.correlation.rules_engine import correlate
from sicg.ingestion.synthetic import generate_cost_events, generate_identity_events
from sicg.storage.repository import SignalRepository

app = FastAPI(
    title="SICG — Sentinel Identity & Cost Guard",
    description="Correlación de gasto en la nube con elevación de privilegios de identidad",
    version="0.1.0",
)

# CORS abierto en el MVP para poder servir el dashboard desde file:// o
# un puerto de dev distinto; restringir a orígenes concretos antes de
# cualquier despliegue real (ver docs/adr para dejarlo documentado).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(signals.router)
app.include_router(summary.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/pipeline/run")
def run_pipeline_endpoint():
    """Dispara el pipeline (hoy sobre datos sintéticos; cuando los
    conectores reales estén validados, esto pasa a usar aws_cost.py /
    aws_iam.py / entra_id.py en vez de synthetic.py) y deja los
    resultados disponibles para /signals y /summary."""
    cost_events = generate_cost_events()
    identity_events = generate_identity_events()
    raw_signals = correlate(identity_events, cost_events)
    scored = score_all(raw_signals)

    repo = SignalRepository()
    repo.save_all(scored)
    set_repo(repo)

    return {"status": "ok", "signals_generated": len(scored)}
