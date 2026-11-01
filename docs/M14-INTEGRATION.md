# M14 — Validación integral

Se incorporan pruebas de integración HTTP reales con FastAPI, el grafo DAG de M13, las políticas de autorización y el planificador con reintentos.

## Ejecución

`pip install -e '.[test,api,api-test]' && pytest -q tests/test_m14_integration.py`

## Alcance y límites

Se prueba el flujo completo petición → ejecución de nodos → resultado → consulta, incluyendo errores, autorización y aislamiento de contextos entre ejecuciones. El adaptador de almacenamiento usado en estas pruebas es **en memoria**, no PostgreSQL; las pruebas PostgreSQL existentes continúan en su workflow separado. Las pruebas de reintentos detallados e idempotencia siguen en sus módulos respectivos. No se prueba despliegue Docker ni agentes LLM reales.
