# M15.2 — Docker Compose Linux (diseño original Hetzner; sandbox remoto actual)

Original design target (01/11/2026): **Hetzner Cloud Linux**. Actual sandbox documented in M18.3 and tested via PuTTY on 22/11/2026: **remote Linux VPS at Hosting.com**. Do not infer the provider from the original M15 design. Windows/Docker Desktop is not the execution host. **M15 is already running** on loopback port 8000 with a private PostgreSQL; the steps below are the historical initial-install procedure, not an instruction to recreate it.

## Components
- `radich`: FastAPI and native Python DAG demo, accessible only on VPS loopback port 8000.
- `postgres`: PostgreSQL 16 on a private Docker network, with a persistent named volume; no host database port.
- Startup waits for PostgreSQL readiness; the API initializes its current tables.
- Each HTTP operation obtains its own PostgreSQL connection; results survive container restarts.

## Initial installation procedure (historical; do not re-run on an existing VPS without authorization)
1. Configure Linux host firewall, SSH keys and Docker Engine/Compose.
2. Copy `.env.example` to `.env` and replace both placeholders with random secrets; protect file permissions.
3. Run `docker compose config` to validate configuration.
4. Run `docker compose up -d --build` on the Linux VPS.
5. Check `docker compose ps` and `curl http://127.0.0.1:8000/health` on the VPS.
6. Submit a POST to `/v1/runs` with `X-API-Key` and `{"initial_payloads":{"extract":{"text":"RADICH"}}}`, then GET `/v1/runs/{run_id}`.
7. Restart the API and repeat GET to verify PostgreSQL persistence.

**Current scope: sandbox, not production.** HTTPS reverse proxy, production hardening, external backups and monitoring remain deferred. A local A01 backup/restoration was verified later, but is not disaster recovery. Port 8000 remains bound only to loopback; do not expose it publicly. PR #12 did not provision a VPS by itself; **M15 was subsequently installed and its `/health` verified**. For the current status see the Drive master: https://docs.google.com/document/d/18URU5hm6g8HwpNiLTEVP46sU2qNCB5b1IisjBYUkEys/edit
