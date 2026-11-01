# RADICH — instrucciones permanentes para desarrollo

## Decisión de infraestructura (obligatoria)

- **RADICH se ejecuta en un VPS Linux remoto de Hetzner Cloud. NO se despliega ni se ejecuta en el ordenador Windows del usuario.**
- Docker Compose debe prepararse para **Linux/Hetzner**, con FastAPI/Python y PostgreSQL en contenedores separados.
- PostgreSQL usa volumen persistente y red privada Docker: **nunca publicar el puerto de PostgreSQL a Internet**.
- Acceso de usuarios mediante navegador/móvil con HTTPS y autenticación. SSH con claves, firewall y secretos fuera del repositorio.
- El equipo Windows del usuario puede servir para acceder o editar, pero **no es un requisito ni el host de ejecución**. No recomendar Docker Desktop ni WSL2 como destino del proyecto.
- **No contratar VPS ni desplegar en Hetzner sin autorización explícita.**

## Fuente de verdad

Antes de proponer infraestructura, consultar en Google Drive `90 - Proyectos / 91 - Radich V00 / 20 - Cerebro` los documentos **RADICH - Modelo de Ejecución v0.3 - Depurado** y **RADICH - Decisiones vigentes Hetzner - 2026-11-01**. Las guías anteriores de Windows/Docker local son históricas y no prevalecen.

## Flujo de trabajo

Código y pruebas en GitHub `VIU-01/RADICH`; arquitectura y decisiones en Drive. Desarrollar mediante ramas y PR; no fusionar sin permiso del usuario. Documentar límites de lo probado y no declarar despliegue sin evidencia.
