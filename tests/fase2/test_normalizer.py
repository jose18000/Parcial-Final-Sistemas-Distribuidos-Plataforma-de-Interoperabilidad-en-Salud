"""
tests/fase2/test_normalizer.py
Normalizador FHIR R4 (guía Fase 2: mínimo 5 casos, incluido uno inválido).
"""

import unittest

from fhir.normalizer import (normalizar_paciente, normalizar_atencion, normalizar_diagnostico,
                             normalizar_tecnologia, construir_bundle_transaccional, bundle_desde_registro)
from traductor.traductor import desde_hl7

RUTA_57 = "tests/datos/06_adt_a03_57_campos_sede1.hl7"


class TestNormalizadorFHIR(unittest.TestCase):

    def setUp(self):
        self.usuario = {"documento_id": "1001", "tipo_documento": "CC", "nombre_completo": "Carlos Perez",
                        "apellidos": "Perez", "nombres": "Carlos", "fecha_nacimiento": "1980-04-12", "sexo": "M",
                        "direccion_residencia": "Calle 22 # 14-30", "telefono": "3001234567", "sede_origen_id": 1}
        self.atencion = {"numero_visita": "V-S1-0150", "clase_atencion": "E", "fecha_ingreso": "2026-11-07T11:00:00",
                         "clasificacion_triage": "2", "sede_id": 1, "estado": "FINALIZADA",
                         "egreso": {"fecha_salida": "2026-11-07T15:30:00", "condicion_salida": "01"}}
        self.dx = {"cie10_codigo": "I10", "descripcion_cie10": "Hipertensión esencial", "rol": "INGRESO",
                   "fecha_diagnostico": "2026-11-07", "numero_visita": "V-S1-0150"}
        self.lab = {"tipo": "LABORATORIO", "loinc_codigo": "718-7", "descripcion_loinc": "Hemoglobina",
                    "valor": 13.8, "unidad": "g/dL", "fecha_toma": "2026-11-07T11:30:00", "numero_visita": "V-S1-0150"}

    def test_caso1_paciente_valido_id_determinista(self):
        p = normalizar_paciente(self.usuario)
        self.assertEqual((p["resourceType"], p["id"], p["gender"]), ("Patient", "pac-1001", "male"))
        self.assertEqual(p["name"][0]["family"], "Perez")
        self.assertEqual(p["identifier"][0]["value"], "1001")
        self.assertEqual(p["managingOrganization"]["reference"], "Organization/org-sede-1")

    def test_caso2_invalido_documento(self):
        for doc, texto in (("ABC123", "debe ser numérico"), ("12", "entre 4 y 15 dígitos")):
            with self.assertRaises(ValueError) as ctx:
                normalizar_paciente({**self.usuario, "documento_id": doc})
            self.assertIn(texto, str(ctx.exception))

    def test_caso3_encounter_clase_triage_y_periodo(self):
        enc = normalizar_atencion(self.atencion, "pac-1001", [self.dx])
        self.assertEqual(enc["id"], "enc-V-S1-0150")
        self.assertEqual(enc["status"], "finished")
        self.assertEqual(enc["class"]["code"], "EMER")
        self.assertEqual(enc["priority"]["coding"][0]["code"], "T2")
        self.assertTrue(enc["period"]["start"].endswith("-05:00"))
        self.assertEqual(enc["diagnosis"][0]["use"]["coding"][0]["code"], "AD")

    def test_caso4_invalido_cie10(self):
        with self.assertRaises(ValueError) as ctx:
            normalizar_diagnostico({**self.dx, "cie10_codigo": "DIARREA"}, "pac-1001", "enc-V-S1-0150")
        self.assertIn("CIE-10 inválido", str(ctx.exception))

    def test_caso5_observation_loinc(self):
        obs = normalizar_tecnologia(self.lab, "pac-1001", "enc-V-S1-0150")
        self.assertEqual(obs["resourceType"], "Observation")
        self.assertEqual(obs["id"], "obs-V-S1-0150-718-7")
        self.assertEqual(obs["code"]["coding"][0]["system"], "http://loinc.org")
        self.assertEqual(obs["valueQuantity"]["value"], 13.8)

    def test_caso6_bundle_transaction_put_y_referencias_internas(self):
        bundle = construir_bundle_transaccional(self.usuario, [self.atencion], [self.dx], [self.lab])
        self.assertEqual((bundle["type"], bundle["id"]), ("transaction", "bundle-pac-1001"))
        ids = set()
        for e in bundle["entry"]:
            r = e["resource"]
            self.assertEqual(e["request"], {"method": "PUT", "url": f"{r['resourceType']}/{r['id']}"})
            ids.add(f"{r['resourceType']}/{r['id']}")
        # Toda referencia apunta a un recurso del mismo Bundle
        def refs(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "reference":
                        yield v
                    else:
                        yield from refs(v)
            elif isinstance(obj, list):
                for x in obj:
                    yield from refs(x)
        for ref in refs(bundle):
            self.assertIn(ref, ids, f"Referencia colgante: {ref}")

    def test_caso7_reenviar_produce_el_mismo_bundle(self):
        b1 = construir_bundle_transaccional(self.usuario, [self.atencion], [self.dx], [self.lab])
        b2 = construir_bundle_transaccional(self.usuario, [self.atencion], [self.dx], [self.lab])
        self.assertEqual(b1, b2)

    def test_caso8_mensaje_57_campos_produce_todos_los_recursos(self):
        _, reg = desde_hl7(open(RUTA_57, encoding="utf-8", newline="").read())
        tipos = [e["resource"]["resourceType"] for e in bundle_desde_registro(reg)["entry"]]
        for t in ("Organization", "Practitioner", "Patient", "Encounter", "Condition", "MedicationRequest",
                  "AllergyIntolerance"):
            self.assertIn(t, tipos)
        self.assertEqual(tipos.count("Condition"), 5)


if __name__ == "__main__":
    unittest.main()
