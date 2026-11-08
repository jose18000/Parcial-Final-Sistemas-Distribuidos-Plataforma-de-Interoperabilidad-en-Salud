"""
tests/fase2/test_normalizer.py
Pruebas unitarias para el normalizador FHIR R4.
Mínimo 5 casos de prueba requeridos por la guía de Fase 2.
"""

import unittest
from fhir.normalizer import (
    normalizar_paciente,
    normalizar_atencion,
    normalizar_diagnostico,
    normalizar_tecnologia,
    construir_bundle_transaccional
)


class TestNormalizadorFHIR(unittest.TestCase):

    def setUp(self):
        self.usuario_valido = {
            "documento_id": "1001",
            "tipo_documento": "CC",
            "nombre_completo": "Perez^Carlos",
            "fecha_nacimiento": "1980-04-12",
            "sexo": "M",
            "direccion": "Calle 22 # 14-30, Sincelejo",
            "telefono": "3001234567",
            "sede_origen_id": 1
        }

        self.atencion_valida = {
            "numero_visita": "V-S1-0150",
            "clase_atencion": "E",
            "fecha_ingreso": "2026-11-07T11:00:00Z",
            "fecha_egreso": "2026-11-07T15:30:00Z",
            "triage": 2,
            "estado": "FINALIZADA",
            "sede_id": 1
        }

        self.dx_valido = {
            "cie10_codigo": "I10",
            "descripcion_cie10": "Hipertensión esencial",
            "fecha_diagnostico": "2026-11-07",
            "numero_visita": "V-S1-0150"
        }

        self.tech_valida = {
            "loinc_codigo": "718-7",
            "descripcion_loinc": "Hemoglobina [Masa/volumen] en sangre",
            "valor": 13.80,
            "unidad": "g/dL",
            "fecha_toma": "2026-11-07T11:30:00Z",
            "numero_visita": "V-S1-0150"
        }

    # Caso 1: Paciente válido con ID determinista y mapeo de género
    def test_caso1_paciente_valido(self):
        paciente = normalizar_paciente(self.usuario_valido)
        self.assertEqual(paciente["resourceType"], "Patient")
        self.assertEqual(paciente["id"], "pac-1001")
        self.assertEqual(paciente["gender"], "male")
        self.assertEqual(paciente["name"][0]["family"], "Perez")
        self.assertEqual(paciente["identifier"][0]["value"], "1001")

    # Caso 2 (Inválido): Documento no numérico o fuera de rango (debe fallar)
    def test_caso2_paciente_documento_invalido(self):
        usuario_invalido = dict(self.usuario_valido)
        usuario_invalido["documento_id"] = "ABC123"  # No numérico
        with self.assertRaises(ValueError) as ctx:
            normalizar_paciente(usuario_invalido)
        self.assertIn("debe ser numérico", str(ctx.exception))

        usuario_invalido["documento_id"] = "12"  # Menos de 4 dígitos
        with self.assertRaises(ValueError) as ctx2:
            normalizar_paciente(usuario_invalido)
        self.assertIn("entre 4 y 15 dígitos", str(ctx2.exception))

    # Caso 3: Atención con clase mapped y referencia exacta al Patient
    def test_caso3_atencion_valida_y_referencia(self):
        enc = normalizar_atencion(self.atencion_valida, "pac-1001")
        self.assertEqual(enc["resourceType"], "Encounter")
        self.assertEqual(enc["id"], "enc-V-S1-0150")
        self.assertEqual(enc["status"], "finished")
        self.assertEqual(enc["class"]["code"], "EMER")
        self.assertEqual(enc["subject"]["reference"], "Patient/pac-1001")
        self.assertEqual(enc["priority"]["coding"][0]["code"], "T2")

    # Caso 4 (Inválido): Diagnóstico con código CIE-10 inválido
    def test_caso4_diagnostico_cie10_invalido(self):
        dx_invalido = dict(self.dx_valido)
        dx_invalido["cie10_codigo"] = "DIARREA_TEXTO_LIBRE"  # No formato CIE-10
        with self.assertRaises(ValueError) as ctx:
            normalizar_diagnostico(dx_invalido, "pac-1001", "enc-V-S1-0150")
        self.assertIn("CIE-10 inválido", str(ctx.exception))

    # Caso 5: Tecnología/Observación con código LOINC y unidad estándar
    def test_caso5_observacion_loinc_valida(self):
        obs = normalizar_tecnologia(self.tech_valida, "pac-1001", "enc-V-S1-0150")
        self.assertEqual(obs["resourceType"], "Observation")
        self.assertEqual(obs["id"], "obs-V-S1-0150-7187")
        self.assertEqual(obs["code"]["coding"][0]["system"], "http://loinc.org")
        self.assertEqual(obs["code"]["coding"][0]["code"], "718-7")
        self.assertEqual(obs["valueQuantity"]["value"], 13.80)
        self.assertEqual(obs["valueQuantity"]["unit"], "g/dL")

    # Caso 6: Bundle transaction completo con método PUT y referencias internas
    def test_caso6_bundle_transaccional_completo(self):
        bundle = construir_bundle_transaccional(
            usuario=self.usuario_valido,
            atenciones=[self.atencion_valida],
            diagnosticos=[self.dx_valido],
            tecnologias=[self.tech_valida]
        )

        self.assertEqual(bundle["resourceType"], "Bundle")
        self.assertEqual(bundle["type"], "transaction")
        self.assertEqual(len(bundle["entry"]), 4)  # Patient, Encounter, Condition, Observation

        # Verificar que todos los recursos usen PUT y tengan URL determinista
        for entry in bundle["entry"]:
            req = entry["request"]
            self.assertEqual(req["method"], "PUT")
            res = entry["resource"]
            self.assertEqual(req["url"], f"{res['resourceType']}/{res['id']}")

        # Verificar consistencia de referencias
        entry_types = [e["resource"]["resourceType"] for e in bundle["entry"]]
        self.assertListEqual(entry_types, ["Patient", "Encounter", "Condition", "Observation"])


if __name__ == "__main__":
    unittest.main()

