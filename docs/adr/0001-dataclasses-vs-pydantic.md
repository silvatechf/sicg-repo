# ADR 0001 — Usar `dataclasses` de la stdlib en vez de Pydantic (temporalmente)

## Estado
Aceptado (temporal — revisar cuando cambie la restricción que lo motivó)

## Contexto
El modelo de datos normalizado (`IdentityEvent`, `CostEvent`, `RiskSignal`)
necesita validación de tipos y una forma limpia de serializar a JSON para
la API y el dashboard. La opción estándar de la industria para esto en
proyectos Python modernos es Pydantic (validación declarativa, integración
nativa con FastAPI, serialización automática).

El entorno donde se desarrolló la primera versión del proyecto no tenía
acceso a red para instalar dependencias vía pip, por lo que Pydantic no
estaba disponible.

## Decisión
Usar `dataclasses` de la librería estándar, con validación manual en
`__post_init__` donde hace falta, y un método `to_dict()` explícito para
serialización en `RiskSignal`.

## Consecuencias
- **Positivo:** cero dependencias externas para el modelo de datos; el
  código corre en cualquier Python 3.11+ sin instalar nada.
- **Negativo:** validación más verbosa y menos exhaustiva que Pydantic
  (no hay coerción automática de tipos, no hay validadores declarativos
  reutilizables, no hay integración automática con la documentación
  OpenAPI que genera FastAPI).
- **Negativo:** FastAPI ya está en el proyecto (ver `api/`) y sí tiene
  Pydantic como dependencia transitiva — hoy conviven dos paradigmas de
  modelado de datos en el mismo repo (dataclasses en `normalization/`,
  Pydantic implícito en las respuestas de FastAPI, que hoy son dicts planos
  en vez de modelos Pydantic explícitos).

## Revisión pendiente
Cuando el entorno de desarrollo tenga acceso a red de forma estable,
evaluar migrar `normalization/schemas.py` a Pydantic `BaseModel`. Ganaría:
validación más estricta, `model_dump()` gratis en vez de `to_dict()` a
mano, y que los routers de `api/` puedan declarar `response_model=` con
los mismos tipos que usa el motor de correlación, en vez de devolver
dicts sueltos.
