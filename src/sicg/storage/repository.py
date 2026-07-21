"""
Repositorio de señales de riesgo. SQLite para el MVP (cero infraestructura
que levantar); la interfaz está pensada para poder cambiar a Postgres en
v1.0 sin tocar el resto del pipeline.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sicg.normalization.schemas import RiskSignal


class SignalRepository:
    def __init__(self, db_path: str = ":memory:"):
        # check_same_thread=False evita erros em testes assíncronos/multithread com FastAPI
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                score REAL NOT NULL,
                reason TEXT NOT NULL,
                correlated INTEGER NOT NULL,
                detected_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def save_all(self, signals: list[RiskSignal]) -> None:
        rows = [
            (
                s.identity_id,
                s.severity.value,
                s.score,
                s.reason,
                int(s.correlated),
                s.detected_at.isoformat(),
                json.dumps(s.to_dict()),
            )
            for s in signals
        ]
        self._conn.executemany(
            """INSERT INTO risk_signals
               (identity_id, severity, score, reason, correlated, detected_at, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._conn.commit()

    def all(self) -> list[dict]:
        cur = self._conn.execute("SELECT payload_json FROM risk_signals ORDER BY score DESC")
        return [json.loads(row[0]) for row in cur.fetchall()]

    def export_json(self, path: str) -> None:
        Path(path).write_text(json.dumps(self.all(), indent=2, ensure_ascii=False))