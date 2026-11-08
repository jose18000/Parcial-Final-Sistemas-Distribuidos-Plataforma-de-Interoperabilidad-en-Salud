# Diagrama 3 · Clases del Dominio

**Responsable:** A — Jose Guillermo Canchila
**Herramienta:** Mermaid `classDiagram`

## Descripción

Muestra las 12 entidades principales del dominio: las 6 tablas clínicas (usuario, atención, diagnóstico, tecnología en salud, egreso, profesional), más las entidades de infraestructura (mensaje del bus, evento de auditoría, sede, Bundle FHIR, usuario del sistema, rol).

> **Supuesto de diseño:** `Usuario` es el paciente en el sistema clínico. `UsuarioSistema` es quien inicia sesión (puede ser médico, admisionista, etc.). Separamos ambos porque un médico nunca es el sujeto de una atención.

## Diagrama

```mermaid
classDiagram
    direction TB

    class Usuario {
        +String documento_id PK
        +String nombre_completo
        +Date fecha_nacimiento
        +String sexo
        +String direccion
        +String telefono
        +String fhir_patient_id
        +Integer sede_origen_id FK
        +DateTime creado_en
    }

    class Atencion {
        +String numero_visita PK
        +String clase_atencion
        +DateTime fecha_ingreso
        +DateTime fecha_egreso
        +Integer triage
        +String estado
        +String fhir_encounter_id
        +String documento_id FK
        +Integer sede_id FK
        +String codigo_profesional FK
    }

    class Diagnostico {
        +UUID id PK
        +String cie10_codigo
        +String descripcion_cie10
        +String tipo
        +Date fecha_diagnostico
        +String fhir_condition_id
        +String numero_visita FK
    }

    class TecnologiaSalud {
        +UUID id PK
        +String loinc_codigo
        +String descripcion_loinc
        +String valor
        +String unidad
        +DateTime fecha_toma
        +String tipo
        +String fhir_observation_id
        +String numero_visita FK
    }

    class Egreso {
        +UUID id PK
        +DateTime fecha_egreso
        +String motivo_egreso
        +String condicion_salida
        +String destino_post_egreso
        +String sello_hash
        +String numero_visita FK
    }

    class ProfesionalSalud {
        +String codigo PK
        +String nombre_completo
        +String especialidad
        +String registro_medico
        +Integer sede_id FK
    }

    class MensajeBus {
        +String mensaje_id PK
        +String formato
        +String sede_origen
        +String tipo_mensaje
        +String estado
        +Integer intentos
        +DateTime recibido_en
        +DateTime entregado_en
        +String hash_contenido
        +String motivo_rechazo
        +String bundle_id FK
    }

    class EventoAuditoria {
        +UUID evento_id PK
        +String tipo_evento
        +String usuario_sistema_id FK
        +String rol
        +String recurso_afectado
        +String resultado
        +DateTime timestamp
        +String hash_anterior
        +String hash_propio
        +String detalle_json
    }

    class Sede {
        +Integer sede_id PK
        +String nombre
        +String ciudad
        +String endpoint_db
        +String endpoint_hsb
        +Boolean activa
    }

    class BundleFHIR {
        +String bundle_id PK
        +String tipo
        +DateTime timestamp
        +String version_fhir
        +Integer total_recursos
        +String documento_paciente FK
    }

    class UsuarioSistema {
        +String usuario_id PK
        +String username
        +String password_hash
        +String nombre_completo
        +Boolean activo
        +Integer sede_id FK
        +String rol_nombre FK
    }

    class Rol {
        +String nombre PK
        +String descripcion
        +String permisos_json
    }

    %% Relaciones clínicas
    Usuario "1" --> "0..*" Atencion : tiene
    Atencion "1" --> "0..*" Diagnostico : incluye
    Atencion "1" --> "0..*" TecnologiaSalud : contiene
    Atencion "1" --> "0..1" Egreso : finaliza_con
    Atencion "0..*" --> "1" ProfesionalSalud : atendido_por
    Atencion "0..*" --> "1" Sede : pertenece_a
    Usuario "0..*" --> "1" Sede : sede_origen

    %% Relaciones de infraestructura
    MensajeBus "0..*" --> "1" Sede : originado_en
    MensajeBus "0..1" --> "1" BundleFHIR : genera
    MensajeBus "1" --> "0..*" EventoAuditoria : registra_en
    BundleFHIR "1" --> "1" Usuario : representa

    %% Relaciones de seguridad
    UsuarioSistema "0..*" --> "1" Rol : tiene_asignado
    UsuarioSistema "0..*" --> "1" Sede : pertenece_a
    EventoAuditoria "0..*" --> "1" UsuarioSistema : ejecutado_por
```

## Notas de diseño

| Decisión | Razón |
|----------|-------|
| `fhir_patient_id` en `Usuario` nullable | Inicia nulo (cobertura FHIR 0 %). Se actualiza cuando el bundle se entrega a HAPI. |
| `hash_anterior` + `hash_propio` en `EventoAuditoria` | Implementa la cadena de auditoría (RF5). Detecta alteración sin Blockchain. |
| `estado` en `MensajeBus` | Refleja exactamente los estados del diagrama de estados (coherencia). |
| `permisos_json` en `Rol` | Flexible para agregar permisos sin migración de esquema. |
| `sello_hash` en `Egreso` | El médico recibe un sello al registrar el egreso (RF6 — vista médico). |

