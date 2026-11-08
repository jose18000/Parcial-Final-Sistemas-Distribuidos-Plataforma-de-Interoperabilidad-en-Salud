# Diagrama 1 · Casos de Uso

**Responsable:** A — Jose Guillermo Canchila
**Herramienta:** Mermaid (renderiza en GitHub/GitLab sin plugins)

## Actores

| Actor | Descripción |
|-------|-------------|
| **Paciente** | Persona atendida; solo puede ver su propia historia |
| **Admisionista** | Personal de admisión y triage; abre atenciones, NO ve diagnósticos |
| **Médico** | Profesional de salud; consulta, diagnostica y da egreso |
| **Auditor** | Perfil de control; verifica integridad y gestiona nodos |
| **SistemaSede** | Sistema legado de cada IPS; emite HL7 v2 y CSV al bus |

## Diagrama

```mermaid
flowchart LR
    PA(["👤\nPaciente"])
    AD(["👤\nAdmisionista"])
    ME(["👤\nMédico"])
    AU(["👤\nAuditor"])
    SS(["🖥️\nSistema\nde Sede"])

    UC1(["UC1\nConsultar historia\nclínica unificada"])
    UC2(["UC2\nDescargar Bundle FHIR\npersonal"])
    UC3(["UC3\nVer accesos\na su historia"])
    UC4(["UC4\nRegistrar admisión\ny triage"])
    UC5(["UC5\nBuscar paciente\npor documento"])
    UC6(["UC6\nVer estado de mensajes\nenviados al bus"])
    UC7(["UC7\nRegistrar diagnóstico\nCIE-10"])
    UC8(["UC8\nRegistrar egreso\ncon sello de auditoría"])
    UC9(["UC9\nOrdenar y formular\ntecnología en salud"])
    UC10(["UC10\nGenerar Reporte HC\nunificado por sede"])
    UC11(["UC11\nVerificar integridad\nde la cadena de auditoría"])
    UC12(["UC12\nVer métricas y estado\nde la plataforma"])
    UC13(["UC13\nGestionar nodos\napagar / encender"])
    UC14(["UC14\nEnviar mensaje\nHL7 v2 o CSV al bus"])

    PA --> UC1
    PA --> UC2
    PA --> UC3

    AD --> UC4
    AD --> UC5
    AD --> UC6

    ME --> UC1
    ME --> UC5
    ME --> UC7
    ME --> UC8
    ME --> UC9
    ME --> UC10
    ME --> UC12

    AU --> UC10
    AU --> UC11
    AU --> UC12
    AU --> UC13

    SS --> UC14

    style PA fill:#4A90D9,color:#fff,stroke:#2c6fad
    style AD fill:#27AE60,color:#fff,stroke:#1a7a42
    style ME fill:#8E44AD,color:#fff,stroke:#5d2d73
    style AU fill:#E67E22,color:#fff,stroke:#a85a18
    style SS fill:#7F8C8D,color:#fff,stroke:#566273
```

## Coherencia con otros diagramas

| Caso de uso | Actor(es) | Clase(s) involucradas | Estado del mensaje |
|-------------|-----------|----------------------|-------------------|
| UC14 · Enviar HL7/CSV | SistemaSede | `MensajeBus`, `Sede` | RECIBIDO → VALIDADO/RECHAZADO |
| UC7 · Registrar diagnóstico | Médico | `Diagnostico`, `Atencion`, `Usuario` | — (escritura directa en BD) |
| UC11 · Verificar auditoría | Auditor | `EventoAuditoria` | — |
| UC10 · Reporte HC | Médico, Auditor, Paciente | Todos los recursos FHIR | ENTREGADO |

> **Nota de diseño:** UC4 (admisionista) y UC7 (médico) están separados deliberadamente.
> Un admisionista NO puede registrar diagnósticos (Regla RF6 y principio de mínimo privilegio).

