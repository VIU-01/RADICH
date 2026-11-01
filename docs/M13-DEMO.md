# RADICH M13 — Demo local reproducible

Este módulo demuestra un DAG determinista de tres nodos: `extract → validate → summarize`.
No usa LLM, red, agentes autónomos ni datos reales.

## Ejecutar

```bash
pip install -e '.[test,api,api-test]'
python -m pytest -q tests/test_demo.py
python - <<'PY'
from radich.demo import build_demo_runner
run_id = "demo-001"
result = build_demo_runner(run_id).run(run_id, {
    "extract": {"text": "RADICH procesa nodos con dependencias"}
})
print(result.state.value)
print(result.outputs["summarize"].payload)
PY
```

## Integración con M12 y M09

La API M12 recibe un `runner` inyectado con método `run(run_id, initial_payloads)`.
El constructor `build_demo_runner(run_id)` crea el contexto de autorización para ese ID.
Para servir peticiones HTTP se necesita una fábrica de runner por solicitud,
aún no incluida en la API M12. No reutilices un runner con contexto fijo entre
ejecuciones HTTP: M11 rechazará los IDs diferentes.

Para persistir resultados, usar `PostgresRunRepository.save_result(result)` tras
la ejecución; este módulo no guarda automáticamente ni crea conexiones.
El adaptador HTTP con PostgreSQL y configuración de despliegue queda pendiente.

## Alcance

Incluye DAG, políticas, rechazo por falta de aprobación y reintentos configurables.
No implementa pausa/reanudación, cola de trabajos, autenticación de actores
externos, persistencia automática ni ejecución de agentes de IA.

## CI

Las pruebas de la demostración se ejecutan en la PR contra main, tras M12.
