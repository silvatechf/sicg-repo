"""
Endpoints relacionados con señales de riesgo.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from sicg.storage.repository import SignalRepository

router = APIRouter(prefix="/signals", tags=["signals"])

# Repositorio compartido a nivel de módulo. En el MVP basta con SQLite
# en memoria por proceso; cuando se migre a Postgres (roadmap, punto 6)
# esto pasa a ser una conexión gestionada por dependencia de FastAPI
# (Depends) en vez de una instancia global.
_repo: SignalRepository | None = None


def get_repo() -> SignalRepository:
    global _repo
    if _repo is None:
        _repo = SignalRepository()
    return _repo


def set_repo(repo: SignalRepository) -> None:
    """Usado por main.py tras correr el pipeline, y por los tests para
    inyectar un repositorio con datos conocidos."""
    global _repo
    _repo = repo


@router.get("")
def list_signals(
    severity: str | None = Query(default=None, description="Filtra por severidad exacta"),
    min_score: float = Query(default=0.0, ge=0.0, le=100.0),
):
    signals = get_repo().all()
    if severity:
        signals = [s for s in signals if s["severity"] == severity.lower()]
    if min_score:
        signals = [s for s in signals if s["score"] >= min_score]
    return {"count": len(signals), "signals": signals}


@router.get("/{identity_id:path}")
def get_signals_for_identity(identity_id: str):
    signals = [s for s in get_repo().all() if s["identity_id"] == identity_id]
    return {"identity_id": identity_id, "count": len(signals), "signals": signals}
