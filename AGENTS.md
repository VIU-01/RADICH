# RADICH — instrucciones permanentes para desarrollo

## Estado del sandbox e infraestructura (22/11/2026)

- **RADICH se ejecuta en un VPS Linux remoto de pruebas identificado como Hosting.com en la guía M18.3 y en las sesiones PuTTY. NO se ejecuta en Windows.** Hetzner Cloud fue la elección de diseño del 01/11/2026; no confundirla con el alojamiento efectivo comprobado después.
- Docker Compose se ejecuta en **Linux remoto**, con servicios FastAPI/Python y PostgreSQL separados. M15 usa `127.0.0.1:8000`; A01 testing, `127.0.0.1:8001`, PostgreSQL y volumen independientes.
- PostgreSQL usa volumen persistente y red privada Docker: **nunca publicar el puerto de PostgreSQL a Internet**.
- Navegador/móvil con HTTPS y autenticación, SSH con claves y firewall son **objetivos de producción pendientes**, no características verificadas del sandbox actual. Las API de pruebas están ligadas a loopback y los secretos deben permanecer fuera del repositorio.
- El equipo Windows del usuario puede servir para acceder o editar, pero **no es un requisito ni el host de ejecución**. No recomendar Docker Desktop ni WSL2 como destino del proyecto.
- **No contratar nuevo alojamiento, desplegar producción ni modificar el VPS sin autorización explícita.** En el sandbox, los despliegues siguen siendo **manuales por PuTTY**; no introducir CD GitHub Actions→VPS sin nueva orden del usuario.

## Fuente de verdad

Antes de proponer cambios, consultar en Drive `90 - Proyectos / 91 - Radich V00 / 20 - Cerebro` **RADICH - 01 Control maestro VIGENTE - M19.1 - 2026-11-22** (https://docs.google.com/document/d/18URU5hm6g8HwpNiLTEVP46sU2qNCB5b1IisjBYUkEys/edit), **RADICH - 02 Arquitectura Core y decisiones VIGENTE** (https://docs.google.com/document/d/1SejPnXFqvZTsHnsYhyjYERfMsQrZ2g2OETYd7hv___A/edit) y las bitácoras M18/M19.1. El Modelo v0.3, la decisión Hetzner y las guías Windows son referencias **históricas**.

## Flujo de trabajo

Código y pruebas en GitHub `VIU-01/RADICH`; arquitectura y decisiones en Drive personal. Desarrollar mediante ramas y PR; **no fusionar sin permiso del usuario**. CI automático sí; **despliegue manual por PuTTY** tras revisión y autorización, con comprobación de M15/A01 y registro de salida. No confundir una PR fusionada con el código instalado ni declarar despliegue sin evidencia. Al cierre M19.1, `main` apuntaba a `4f504da158e71a078bc86b141a769667461b8507` (PR #18, seis checks correctos) y A01 se validó con GET `/progress` 401/200/404.
