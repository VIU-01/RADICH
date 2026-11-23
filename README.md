# RADICH

RADICH Core — Python/FastAPI, grafo DAG nativo y PostgreSQL. Está desplegado **solo como sandbox de desarrollo** en un VPS Linux remoto, cuya contratación en **my.hosting** fue confirmada por el usuario el 23/11/2026; es del mismo tipo que el plan contemplado inicialmente en Hetzner. Los manuales iniciales M18 lo llaman «Hosting.com». M15 demo y A01 simulado permanecen independientes. No es un sistema productivo; no hay verificación documental de la marca comercial, plan exacto, región o precio.

- Repositorio de código, CI y PR: [GitHub RADICH](https://github.com/VIU-01/RADICH).
- Estado operativo y cronología comprobada: [Control maestro vigente en Drive](https://docs.google.com/document/d/18URU5hm6g8HwpNiLTEVP46sU2qNCB5b1IisjBYUkEys/edit).
- Arquitectura confirmada: [Arquitectura vigente en Drive](https://docs.google.com/document/d/1SejPnXFqvZTsHnsYhyjYERfMsQrZ2g2OETYd7hv___A/edit).
- Última función integrada al corte documental: M19.1 (PR #18, commit `4f504da`), GET autenticado de progreso A01. El despliegue y la aceptación funcional por PuTTY se registran en el [log M19.1](https://docs.google.com/document/d/1J0LXl1hyOz9wrcpsddibKhKQYsA-DeyQCVpRxlvvIUQ/edit).

**Flujo de cambios:** ramas y PR → CI → fusión previa aprobación → **despliegue manual por PuTTY** → verificaciones → documentación. GitHub Actions ejecuta pruebas, pero no actualiza el VPS automáticamente. Mantener M15 separado de A01.
