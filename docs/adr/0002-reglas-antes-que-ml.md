# ADR 0002 — Motor de correlación basado en reglas, no en ML, para el MVP

## Estado
Aceptado

## Contexto
El objetivo del SICG es detectar cuándo una identidad (usuario, rol,
service principal) escala privilegios y, poco después, genera un gasto
anómalo — un patrón que suele indicar cuenta comprometida o abuso interno.
Existen dos enfoques habituales para esto:

1. **Basado en reglas**: umbrales estadísticos (desviación estándar sobre
   el baseline histórico) + ventana temporal de correlación entre tipos
   de evento concretos.
2. **Basado en ML**: modelos de detección de anomalías (Isolation Forest,
   autoencoders, etc.) entrenados sobre el histórico de eventos.

El motor de respuesta (`response/notifiers.py`) puede llegar a recomendar
revocar credenciales. Es una acción con consecuencias reales para un
usuario o servicio de producción.

## Decisión
Para el MVP y v1.0, el motor de correlación (`correlation/rules_engine.py`)
usa únicamente reglas explicables:
- Detección de picos de gasto por desviación estándar sobre el baseline
  de esa identidad (excluyendo el propio evento evaluado — ver el bug
  corregido durante el testing inicial).
- Correlación temporal entre un evento de identidad "sensible" (de una
  lista explícita y mantenida a mano) y un pico de gasto, dentro de una
  ventana de 2 horas.
- Scoring ponderado con pesos fijos y documentados (`risk_scoring.py`),
  no aprendidos.

Un modelo de ML de detección de anomalías queda fuera de alcance
deliberadamente hasta v1.1 o posterior, y solo como señal complementaria
al motor de reglas, nunca como sustituto.

## Consecuencias
- **Positivo:** cada señal que genera el sistema viene con una frase
  explicable ("evento sensible X seguido de pico de gasto Y, N minutos
  después") — auditable por un humano antes de aprobar cualquier acción.
- **Positivo:** no requiere datos históricos de entrenamiento ni
  reentrenamiento periódico; funciona desde el primer despliegue.
- **Negativo:** las reglas fijas no capturan patrones de abuso más
  sutiles que un modelo de ML sí podría aprender (p. ej. combinaciones
  de eventos de baja severidad individual pero sospechosas en conjunto).
- **Negativo:** los umbrales (ventana de 2h, 3 desviaciones estándar,
  pesos del scoring) están fijados a mano y necesitan recalibrarse con
  datos reales de producción — hoy son un punto de partida razonable,
  no un valor validado empíricamente.

## Revisión pendiente
Reevaluar cuando haya suficiente volumen de datos reales (post-conectores
AWS/Entra validados) para entrenar y validar un modelo de anomalías como
capa complementaria — nunca como reemplazo del motor de reglas explicable.
