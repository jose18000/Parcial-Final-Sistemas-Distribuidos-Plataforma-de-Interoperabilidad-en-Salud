// db/sede2/init-mongo.js
// Sede 2 · Cartagena · MongoDB (mongo_sede2) — nodo NO relacional de la red.
//
// Modelo documental: UN documento por paciente en la colección `pacientes`, con sus
// atenciones embebidas (y dentro de cada atención: diagnósticos, tecnologías y egreso).
// Los nombres de campo NO son los de PostgreSQL (identificacion.numero en vez de documento_id,
// ingreso.fecha en vez de fecha_ingreso...): el traductor universal (traductor/catalogo_57.py)
// sabe convertir entre ambos.
//
// Datos 100 % sintéticos. fhir_patient_id en null: la cobertura FHIR arranca en 0 %.

db = db.getSiblingDB("clinica_cartagena");

db.createCollection("pacientes");
db.createCollection("mensajes_bus");
db.createCollection("profesionales");
db.createCollection("sedes");

// Índices: búsqueda por documento e idempotencia del bus
db.pacientes.createIndex({ "identificacion.numero": 1 }, { unique: true });
db.pacientes.createIndex({ "atenciones.numero_visita": 1 });
db.mensajes_bus.createIndex({ hash_contenido: 1 }, { unique: true });
db.mensajes_bus.createIndex({ estado: 1 });

db.sedes.insertMany([
  { _id: 1, nombre: "IPS Sincelejo Central",    ciudad: "Sincelejo", codigo_prestador: "700010000101", motor: "postgresql" },
  { _id: 2, nombre: "IPS Cartagena Bocagrande", ciudad: "Cartagena", codigo_prestador: "130010000202", motor: "mongodb" },
  { _id: 3, nombre: "IPS Corozal La Perla",     ciudad: "Corozal",   codigo_prestador: "702150000303", motor: "postgresql" }
]);

db.profesionales.insertMany([
  { _id: "MED-02", nombre: "Dr. Mateo Ruiz",      especialidad: "Neumología", registro: "RM-20831-CTG" },
  { _id: "MED-05", nombre: "Dra. Patricia Gomez", especialidad: "Pediatría",  registro: "RM-22190-CTG" }
]);

db.pacientes.insertMany([
  {
    // Paciente 1001: su segunda sede (también tiene atenciones en Sincelejo y Corozal)
    _id: "1001",
    identificacion: { tipo: "CC", numero: "1001" },
    nacionalidad: "CO",
    nombre: { completo: "Carlos Perez", apellidos: "Perez", nombres: "Carlos" },
    nacimiento: { fecha: "1980-04-12", edad: 46, unidad_edad: "1" },
    sexo_biologico: "M",
    identidad_genero: "01",
    ocupacion: "Docente",
    residencia: { pais: "CO", municipio_dane: "70001", zona: "01", direccion: "Calle 22 # 14-30, Sincelejo" },
    contacto: { telefono: "3001234567", correo: "carlos.perez@correo.test" },
    responsable: { nombre: "Ana Perez", parentesco: "03", telefono: "3007654321" },
    fhir_patient_id: null,
    sede_origen: 1,
    atenciones: [
      {
        numero_visita: "V-S2-0080",
        aseguradora: "Nueva EPS",
        ingreso: { fecha: "2026-08-20T14:00:00", modalidad: "01", entorno: "02", via: "02",
                   causa: "Disnea leve, remitido para valoración por neumología" },
        clase_hl7: "O",
        profesional: { codigo: "MED-02" },
        sede: 2,
        estado: "FINALIZADA",
        fhir_encounter_id: null,
        diagnosticos: [
          { id: "cond-V-S2-0080-ing-J45.9", cie10: "J45.9", descripcion: "Asma, no especificada",
            rol: "INGRESO", tipo: "01", orden: 1, fecha: "2026-08-20" },
          { id: "cond-V-S2-0080-egr-J45.9", cie10: "J45.9", descripcion: "Asma, no especificada",
            rol: "EGRESO", tipo: "01", orden: 1, fecha: "2026-08-20" }
        ],
        tecnologias: [
          { id: "obs-V-S2-0080-1988-5", tipo: "LABORATORIO", loinc: "1988-5",
            prueba: "Proteína C reactiva en suero o plasma", resultado: { valor: 2.1, unidad: "mg/L" },
            fecha: "2026-08-20T14:30:00" },
          { id: "med-V-S2-0080-salbutamol", tipo: "MEDICAMENTO", medicamento: "Salbutamol 100 mcg inhalador",
            dosis: "2 inhalaciones", via: "06", frecuencia: "Cada 6 horas si hay disnea", dias_tratamiento: 10,
            unidades: 1, prescriptor: "MED-02", finalidad: "01" }
        ],
        egreso: {
          fecha: "2026-08-20T15:00:00", condicion: "01", codigo_prestador: "130010000202",
          alergias: "Penicilina", antecedentes_familiares: "Madre con asma",
          responsable: "Dr. Mateo Ruiz"
        }
      }
    ]
  },
  {
    // Paciente que solo existe en la sede 2 (Mongo)
    _id: "1005",
    identificacion: { tipo: "TI", numero: "1005" },
    nacionalidad: "CO",
    nombre: { completo: "Luis Herrera Cano", apellidos: "Herrera Cano", nombres: "Luis" },
    nacimiento: { fecha: "2012-03-08", edad: 14, unidad_edad: "1" },
    sexo_biologico: "M",
    residencia: { pais: "CO", municipio_dane: "13001", zona: "01", direccion: "Barrio Manga Calle 25, Cartagena" },
    contacto: { telefono: "3201112233" },
    responsable: { nombre: "Rosa Cano", parentesco: "01", telefono: "3201112244" },
    fhir_patient_id: null,
    sede_origen: 2,
    atenciones: [
      {
        numero_visita: "V-S2-0090",
        aseguradora: "Coosalud EPS",
        ingreso: { fecha: "2026-09-02T09:20:00", modalidad: "01", entorno: "02", via: "01",
                   causa: "Control pediátrico por tos persistente" },
        clase_hl7: "O",
        profesional: { codigo: "MED-05" },
        sede: 2,
        estado: "EN_CURSO",
        fhir_encounter_id: null,
        diagnosticos: [
          { id: "cond-V-S2-0090-ing-J45.9", cie10: "J45.9", descripcion: "Asma, no especificada",
            rol: "INGRESO", tipo: "01", orden: 1, fecha: "2026-09-02" }
        ],
        tecnologias: []
      }
    ]
  }
]);

print("Sede 2 (MongoDB) inicializada: " + db.pacientes.countDocuments() + " pacientes");
