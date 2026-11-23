# M18 — A01/M17.5: despliegue para TESTING (VPS Linux contratado en my.hosting)

**Estado actualizado (23/11/2026): M18 A01 TEST instalada y validada en sandbox.** El usuario confirma la contratación final del VPS en **my.hosting**, de tipo equivalente al plan Hetzner inicialmente estudiado. El manual M18.3 utilizó «Hosting.com» como referencia histórica; no se presume identidad comercial entre marcas. No hay confirmación aquí del plan, región o precio.  PR #16 fusionada (commit `e566d59`), y actualización posterior M19.1 PR #18 fusionada (commit `4f504da`) **desplegada manualmente solo en A01**. CI de `main` 6/6 correctos; en el VPS M15/A01 `/health` OK y `/progress` A01 pasó 401/200/404. El texto siguiente conserva el procedimiento de **primera instalación** para trazabilidad; no volver a ejecutarlo como si el servicio aún no existiera.

Esta microtarea activa de forma controlada el **agente simulado A01** (skill local `text.normalize`) y la persistencia/checkpoints M17.5 en un **segundo servicio independiente**. No hay LLM, acceso a herramientas externas, ni razonamiento autónomo.

## Qué preserva

| Servicio | Actual M15 | A01/M17.5 de testing |
| --- | --- | --- |
| API | `127.0.0.1:8000` | `127.0.0.1:8001` |
| Docker Compose | `compose.yaml` (sin cambios) | `compose.a01-testing.yaml` optativo, perfil `a01-test` |
| PostgreSQL | `postgres` / base `radich` | `postgres-a01` / base `radich_a01` |
| Volumen | `radich_postgres_data` | `radich_postgres_a01_data` |
| Graph | extract → validate → summarize | extract → agent_a01 |
| Seguridad HTTP | X-API-Key M15 | X-API-Key independiente A01; 401 sin ella; 422 input no permitido |

Ninguna base publica el puerto 5432. No hay HTTPS público ni interfaz web. **No utilizar datos reales ni confidenciales.** PuTTY por contraseña, UFW y autenticación web siguen diferidos a producción por decisión del usuario; no publicar la API de testing.

## Puertas de control ANTES del despliegue

1. PR revisada, **fusionada solo tras permiso expreso**, y los trabajos CI de esta PR terminados correctamente.
2. `/opt/radich` limpio, backup de la demo M15 guardado; conservar SHA de rollback.
3. `/opt/radich/.env` contiene `POSTGRES_PASSWORD` y `RADICH_API_KEY` de M15, **además de** `RADICH_A01_POSTGRES_PASSWORD` y `RADICH_A01_API_KEY`, cada una con valor nuevo y distinto del de M15. Permisos `0600`. Nunca mostrar ni copiar secretos.
4. `sudo docker compose ps` muestra demo M15 y PostgreSQL saludables; `/health` en `127.0.0.1:8000` OK.

## Preparación inicial de credenciales A01 (histórica; NO regenerar en el VPS existente)

`compose.a01-testing.yaml` toma los secretos **exclusivamente** de `RADICH_A01_API_KEY` y `RADICH_A01_POSTGRES_PASSWORD`; dentro del contenedor se inyectan como `RADICH_API_KEY` y `POSTGRES_PASSWORD` de A01 para mantener compatibilidad con la aplicación. El `compose.yaml` de M15 sigue utilizando sus valores originales. La falta de cualquiera de las variables A01 debe detener el arranque, nunca reutilizar las de M15.

No crear ni guardar credenciales reales en GitHub, Drive o el chat. El siguiente bloque fue diseñado **solo para el primer alta**; las credenciales A01 ya existen en el VPS sandbox y **no se deben regenerar ni reemplazar**. Para un VPS nuevo, únicamente tras autorización explícita se podrían crear una vez: 

```bash
cd /opt/radich
umask 077
python3 - <<'PY'
from pathlib import Path
import secrets, os
p = Path(".env")
if not p.is_file():
    raise SystemExit("ERROR: falta el .env privado de M15")
lines = p.read_text(encoding="utf-8").splitlines()
names = {line.partition("=")[0].strip() for line in lines if "=" in line and not line.lstrip().startswith("#")}
required = {"RADICH_API_KEY", "POSTGRES_PASSWORD"}
new = {"RADICH_A01_API_KEY", "RADICH_A01_POSTGRES_PASSWORD"}
if not required <= names:
    raise SystemExit("ERROR: faltan variables de M15")
if names & new:
    raise SystemExit("ERROR: las variables A01 ya existen; revisar manualmente sin sobrescribir")
with p.open("a", encoding="utf-8") as stream:
    stream.write("\nRADICH_A01_API_KEY=" + secrets.token_hex(32))
    stream.write("\nRADICH_A01_POSTGRES_PASSWORD=" + secrets.token_hex(32) + "\n")
os.chmod(p, 0o600)
print("OK: credenciales A01 creadas en .env (valores no mostrados)")
PY
```

Para claves ya existentes, comprobar manualmente que son diferentes de las de M15 antes de arrancar. `docker compose ... config -q` valida las variables obligatorias sin imprimir sus valores. No regenerar contraseñas después de inicializar `postgres-a01` sin una rotación coordinada: PostgreSQL conserva la contraseña anterior en su volumen.

## Instalación inicial en el VPS (procedimiento histórico; no repetir ciegamente)

Todos los comandos son Linux, mediante PuTTY y el usuario `radich`.

```bash
cd /opt/radich
git status --short
git rev-parse HEAD
# Solo con PR aprobada y fusionada:
git fetch origin main
git merge --ff-only origin/main
sudo docker compose -f compose.yaml -f compose.a01-testing.yaml --profile a01-test config -q
sudo docker compose -f compose.yaml -f compose.a01-testing.yaml --profile a01-test up -d --build radich-a01
sudo docker compose -f compose.yaml -f compose.a01-testing.yaml --profile a01-test ps
curl -fsS http://127.0.0.1:8001/health
```

`up -d --build radich-a01` solicita **solo el servicio A01 y su dependencia postgres-a01**; no recrea `radich` ni `postgres`. Puede tardar unos segundos en llegar a `healthy`. El perfil nuevo requiere dos contenedores adicionales, por lo que hay que vigilar RAM y disco en un VPS de 4 GB.

### Pruebas automatizadas futuras sin imprimir claves

```bash
cd /opt/radich
python3 scripts/m18_a01_smoke.py create /tmp/radich-a01-smoke-id
# Confirmar resultado de la primera prueba antes del reinicio.
sudo docker compose -f compose.yaml -f compose.a01-testing.yaml --profile a01-test restart radich-a01 postgres-a01
python3 scripts/m18_a01_smoke.py verify /tmp/radich-a01-smoke-id
```

Comprueba 401 sin credenciales, 422 al pedir un campo/herramienta no autorizada, normalización de texto ficticio, lectura después del reinicio y respuesta de `resume` de un run terminado sin re-ejecución. **La recuperación de una ejecución interrumpida por crash** se valida aparte con pruebas M17.5 de CI; esta prueba no la reproduce en el VPS.

### Verificación de aislamiento

```bash
sudo docker compose -f compose.yaml -f compose.a01-testing.yaml --profile a01-test port radich-a01 8000
sudo docker compose -f compose.yaml -f compose.a01-testing.yaml --profile a01-test ps
curl -fsS http://127.0.0.1:8000/health
```

Se espera `127.0.0.1:8001` para A01, PostgreSQL A01 solo interno y M15 aún healthy en 8000.

## Reversión sin pérdida de datos

Solo detener servicios nuevos, sin modificar M15:

```bash
cd /opt/radich
sudo docker compose -f compose.yaml -f compose.a01-testing.yaml --profile a01-test stop radich-a01 postgres-a01
sudo docker compose ps
curl -fsS http://127.0.0.1:8000/health
```

El volumen A01 permanece para diagnóstico o copia. **NUNCA** ejecutar `docker compose down -v`, `docker volume prune` ni borrar el volumen principal. Retirar datos de testing solo mediante una tarea de limpieza explícitamente autorizada.

## Límites y aceptación

- Sin despliegue automático desde GitHub: la PR #16 no cambió el VPS por sí sola, pero el usuario instaló A01 posteriormente por PuTTY y desplegó M19.1 tras la PR #18. La CI de pruebas sí continúa automática.
- A01 usa credenciales API y PostgreSQL **distintas** de M15; la comprobación HTTP rechaza la clave de M15. La ausencia de secretos A01 provoca fallo de configuración, sin fallback.
- A01 usa autorización de skill en el **servidor**, no elegida por el usuario HTTP.
- La llamada `resume` de un resultado terminal devuelve el resultado existente, no reejecuta efectos.
- La base A01 es **otra instancia de PostgreSQL con su propio volumen**. El `radich_test.dump` anterior solo respalda la demo M15, no este servicio nuevo.
- No se garantizan efectos externos exactly-once, ni recuperación ante pérdida del VPS sin backup externo.
- La CI de la PR #18 y la CI posterior de `main` verificaron seis jobs correctamente, incluidos A01 Compose, M17 integración y recuperación. La comprobación de salud y la API de `/progress` se verificaron además en el VPS mediante PuTTY.
- **Producción:** HTTPS, SSH endurecido, UFW y autenticación web requeridos antes de exponer ninguna API.

**Referencia histórica de M17.5:** `src/radich/agents/service.py`, `tests/test_m17_5_postgres.py`, commit `fafea18581d640ee41ba1a6e80d70d2a4b9eebed`. **Estado instalado después:** `4f504da158e71a078bc86b141a769667461b8507`. Para una actualización exclusiva de A01, usar `docker compose -f compose.yaml -f compose.a01-testing.yaml --profile a01-test up -d --build --no-deps radich-a01` tras `git merge --ff-only origin/main`, esperando a `healthy`. No usar `down -v` ni cambiar claves de las bases. Bitácora: https://docs.google.com/document/d/1J0LXl1hyOz9wrcpsddibKhKQYsA-DeyQCVpRxlvvIUQ/edit
