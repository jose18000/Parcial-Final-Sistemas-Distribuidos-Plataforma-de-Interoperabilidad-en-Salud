# app/

API Gateway y vistas por rol — Fase 4-5.

Vistas a implementar:
1. Vista Paciente: historia unificada + descarga Bundle FHIR + log de accesos
2. Vista Admisionista: búsqueda, registro/admisión, estado de mensajes del bus
3. Vista Médico: historia unificada + diagnóstico + egreso con sello
4. Reporte HC: por sede, cobertura FHIR, verificador de auditoría, tablero

REGLA: ninguna vista habla directamente con las BD de las sedes.
Todo pasa por la API (este servicio).

