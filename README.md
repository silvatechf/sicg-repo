# SICG — Sentinel Identity & Cost Guard

Sistema de gobernanza que correlaciona anomalías de gasto en la nube (AWS)
con elevación de privilegios de identidad (IAM / Entra ID), para detectar
patrones que suelen indicar compromiso de cuenta o abuso interno: alguien
escala permisos **y**, poco después, dispara un gasto muy por encima de su
baseline habitual.

Proyecto de portafolio orientado al mercado de seguridad/FinOps.

---

## Estado actual (20/07/2026)

✅ Estructura del repo definida (ingestión → normalización → correlación → respuesta → storage)

✅ Pipeline funcional de punta a punta, corriendo sobre datos sintéticos

✅ Motor de reglas + scoring de riesgo, con 11 tests unitarios en verde

✅ Dashboard funcional con datos reales generados por el pipeline

✅ ADRs escritos (0001 dataclasses-vs-pydantic, 0002 reglas-antes-que-ml)

✅ Workflow de CI/CD escrito (`.github/workflows/ci.yml`) — YAML validado 

🟡 Conectores reales escritos (`aws_cost.py`, `aws_iam.py`, `entra_id.py`) y API con FastAPI
   (`api/main.py`, `api/routers/`) — código completo con boto3/msal/fastapi, con tests
   (mocks para conectores, `TestClient` para la API), 
   el entorno donde se escribieron no tiene acceso a red para instalar esas librerías.
   Sintaxis verificada (`py_compile`), lógica no verificada en ejecución real.
   **El propio workflow de CI (`ci.yml`) es justamente lo que debe validar esto en
   cuanto se haga el primer push a GitHub — instala dependencias reales y corre todo.**

⬜ Persistencia real (Postgres) en vez de SQLite en memoria

⬜ threat-model.md

⬜ Probar los conectores contra una cuenta AWS / tenant Entra real (sandbox, no producción)

## Cómo correrlo

```bash
# instalar dependencias (necesita red — boto3, msal, requests)
pip install -e .

# tests (los de synthetic/correlation corren sin credenciales;
# los de aws_cost/aws_iam/entra_id usan mocks, tampoco necesitan credenciales reales)
cd sicg
PYTHONPATH=src python3 -m unittest discover -s tests/unit -v

# pipeline completo con datos sintéticos (genera dashboard_data.json)
PYTHONPATH=src python3 -m sicg.pipeline
```

### Levantar la API

```bash
PYTHONPATH=src uvicorn sicg.api.main:app --reload
# POST http://localhost:8000/pipeline/run   -> corre el pipeline (hoy con datos sintéticos)
# GET  http://localhost:8000/signals        -> lista señales, filtrable por ?severity= y ?min_score=
# GET  http://localhost:8000/summary        -> agregados para el dashboard
# GET  http://localhost:8000/health
```

### CI/CD

`.github/workflows/ci.yml` corre en cada push/PR a `main`: instala dependencias,
lint con `ruff`, tests unitarios, verifica que el pipeline corre de punta a punta,
y un smoke test que levanta la API real y comprueba `/health`. Matriz sobre
Python 3.11 y 3.12.

### Activar los conectores reales

Los conectores (`ingestion/aws_cost.py`, `aws_iam.py`, `entra_id.py`) implementan
la misma interfaz que `synthetic.py` — sustituir uno por otro en `pipeline.py`
no requiere tocar `correlation/` ni `response/`.

**AWS** (Cost Explorer + CloudTrail): usa la cadena de credenciales estándar de
boto3 (perfil de `~/.aws/credentials`, variables `AWS_*`, o rol de IAM). Además:
- Activar la cost allocation tag `aws:createdBy` en Billing > Cost allocation tags
  (tarda hasta 24h en empezar a poblarse tras activarla)
- El rol/usuario que ejecute SICG necesita permisos `ce:GetCostAndUsage` y
  `cloudtrail:LookupEvents`

**Entra ID** (Microsoft Graph): requiere una app registration con permiso de
aplicación `AuditLog.Read.All` (con consentimiento de administrador), y estas
variables de entorno:
```bash
export SICG_ENTRA_TENANT_ID=...
export SICG_ENTRA_CLIENT_ID=...
export SICG_ENTRA_CLIENT_SECRET=...
```

El dashboard (`dashboard.html`) es estático y lee un JSON embebido; hoy se
regenera a mano copiando la salida del pipeline. Ver "Próximos pasos" para
automatizar esto.

## Estructura del repo

```
sicg/
├── src/sicg/
│   ├── ingestion/        # Adquisición de datos (hoy: sintéticos; mañana: AWS/Entra reales)
│   ├── normalization/    # Modelos comunes (IdentityEvent, CostEvent, RiskSignal)
│   ├── correlation/      # rules_engine.py (detección) + risk_scoring.py (scoring)
│   ├── response/         # Notificación + recomendación de acción (con guardrails)
│   ├── storage/          # Repositorio SQLite
│   └── pipeline.py       # Orquestador end-to-end
├── tests/unit/
├── docs/adr/              # Decisiones de arquitectura (pendiente de rellenar)
└── dashboard.html
```

## Decisiones de diseño ya tomadas

- **Reglas explicables antes que ML.** El motor de correlación (`rules_engine.py`)
  usa desviación estándar sobre el baseline histórico + ventana temporal, no un
  modelo de ML. Un sistema que puede recomendar revocar credenciales tiene que
  poder explicar en una frase por qué se disparó.
- **`dataclasses` en vez de Pydantic para el MVP.** Decisión forzada por el
  entorno de desarrollo actual (sin acceso a red para instalar dependencias),
  no por preferencia de diseño. Revisar cuando haya conectividad real.
- **Kill switch automático desactivado por defecto.** `maybe_recommend_action()`
  solo ejecuta una acción automática si se activa explícitamente
  `auto_response_enabled=True` Y el score supera el umbral. Por defecto siempre
  recomienda y espera aprobación humana.
- **Baseline por evento, excluyendo el propio evento.** Bug real encontrado en
  testing: calcular la media incluyendo el pico que se está evaluando lo
  auto-enmascara. Corregido en `find_cost_spikes()`.


## El problema que resuelve

Las herramientas de CIEM (Cloud Infrastructure Entitlement Management) y
las de FinOps casi siempre viven en silos separados: una analiza permisos,
la otra analiza gasto, y ninguna de las dos ve la señal más obvia de
abuso — que ambas cosas pasen casi a la vez para la misma identidad.

## Documentación

- **[docs/architecture.md](docs/architecture.md)** — diagrama de flujo de datos y decisiones de diseño con impacto arquitectónico
- **[docs/adr/](docs/adr/)** — Architecture Decision Records


## Próximos pasos 

Pendiente de decidir orden de prioridad — estas son las piezas que faltan:

1. ~~Conector real de AWS Cost Explorer~~ — escrito, pendiente de validar en entorno con red
2. ~~Conector real de AWS IAM/CloudTrail~~ — escrito, pendiente de validar
3. ~~Conector de Entra ID~~ — escrito, pendiente de validar
4. ~~API con FastAPI~~ — escrita (`/signals`, `/summary`, `/pipeline/run`, `/health`), pendiente de validar
5. ~~ADRs formales~~ — 0001 y 0002 escritos en `docs/adr/`
6. ~~CI/CD~~ — `.github/workflows/ci.yml` escrito, valida todo lo de arriba en el primer push
7. **Hacer el primer push a un repo real de GitHub y dejar que el CI valide todo lo marcado como "pendiente de validar" arriba** — este es el paso que de verdad cierra el ciclo
8. **Persistencia real** — migrar `storage/repository.py` de SQLite a Postgres
9. **threat-model.md** — modelo de amenazas del propio SICG (quién podría abusar de un sistema que puede revocar credenciales)
10. Conectar `dashboard.html` a la API en vivo (`GET /summary`, `GET /signals`) en vez de JSON embebido a mano
