# M15.2 — Docker Compose (Hetzner Linux)

Target: **remote Linux VPS on Hetzner Cloud**. Windows/Docker Desktop is **not** the execution host.

## Components
- `radich`: FastAPI and native Python DAG demo, accessible only on VPS loopback port 8000.
- `postgres`: PostgreSQL 16 on a private Docker network, with a persistent named volume; no host database port.
- Startup waits for PostgreSQL readiness; the API initializes its current tables.
- Each HTTP operation obtains its own PostgreSQL connection; results survive container restarts.

## Preparation (only after deployment authorization)
1. Configure Linux host firewall, SSH keys and Docker Engine/Compose.
2. Copy `.env.example` to `.env` and replace both placeholders with random secrets; protect file permissions.
3. Run `docker compose config` to validate configuration.
4. Run `docker compose up -d --build` on the Linux VPS.
5. Check `docker compose ps` and `curl http://127.0.0.1:8000/health` on the VPS.
6. Submit a POST to `/v1/runs` with `X-API-Key` and `{"initial_payloads":{"extract":{"text":"RADICH"}}}`, then GET `/v1/runs/{run_id}`.
7. Restart the API and repeat GET to verify PostgreSQL persistence.

**Not production-ready:** HTTPS reverse proxy, external backups, recovery, monitoring, and credential rotation are outside this change. Do not expose port 8000 publicly. This branch does not deploy or provision Hetzner.
