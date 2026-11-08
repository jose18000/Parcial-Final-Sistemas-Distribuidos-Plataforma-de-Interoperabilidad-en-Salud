"""
tests/fase3/test_hsb_integration.py
Pruebas de integración del Health Service Bus (HSB).

Valida el contrato estricto de los 4 archivos de ejemplo:
1. 01_adt_a01_valido_sede2.hl7        -> Entregado (Patient 1007, Encounter, Condition J45.9 en sede 2)
2. 02_oru_r01_laboratorio_sede1.hl7   -> Entregado (Observation LOINC 718-7 = 13,8 g/dL, pac 1001 en sede 1)
3. 03_adt_a01_invalido.hl7           -> Rechazado con 3 motivos
4. 04_sede3_legado.csv                -> 3 entregados (1008, 1009, 1010) y 2 rechazados
5. Prueba de Idempotencia             -> Reenvío del 01 responde 'duplicado'
6. Prueba de Reintentos y Dead Letter -> Simulación de caída de HAPI -> reintentos -> estado MUERTO -> reencolar
"""

import os
import unittest
from hsb.parser_hl7 import parse_hl7_message
from hsb.parser_csv import parse_csv_rows
from hsb.validator import validar_mensaje_pre_transformacion
from hsb.queue_manager import (
    verificar_idempotencia,
    registrar_estado_mensaje,
    procesar_entrega_con_reintentos,
    reencolar_mensaje,
    _MEMORIA_MENSAJES
)
from fhir.normalizer import construir_bundle_transaccional


class TestHSBIntegracion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Determinar ruta base a ejemplos
        cls.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cls.ejemplos_dir = os.path.join(cls.base_dir, "ejemplos")

    def setUp(self):
        # Limpiar almacén en memoria antes de cada prueba
        _MEMORIA_MENSAJES.clear()

    # 1. Archivo 01: ADT^A01 Válido Sede 2
    def test_01_adt_a01_valido_sede2(self):
        ruta = os.path.join(self.ejemplos_dir, "01_adt_a01_valido_sede2.hl7")
        with open(ruta, "r", encoding="utf-8") as f:
            raw = f.read()

        parsed = parse_hl7_message(raw)
        self.assertEqual(parsed["sede_origen"], 2)
        self.assertEqual(parsed["usuario"]["documento_id"], "1007")
        self.assertEqual(parsed["usuario"]["sexo"], "F")
        self.assertEqual(parsed["diagnosticos"][0]["cie10_codigo"], "J45.9")

        # Validación
        es_valido, motivos = validar_mensaje_pre_transformacion(parsed)
        self.assertTrue(es_valido, f"El mensaje debería ser válido. Motivos: {motivos}")
        self.assertEqual(len(motivos), 0)

        # Normalización a FHIR
        bundle = construir_bundle_transaccional(
            usuario=parsed["usuario"],
            atenciones=[parsed["atencion"]],
            diagnosticos=parsed.get("diagnosticos")
        )
        self.assertEqual(bundle["id"], "bundle-pac-1007")

        # Entrega exitosa (simulada o real)
        registrar_estado_mensaje(
            mensaje_id=parsed["mensaje_id"],
            formato="HL7_V2",
            sede_id=2,
            tipo_mensaje="ADT_A01",
            estado="ENTREGADO",
            hash_contenido=parsed["hash_contenido"],
            intentos=1,
            bundle_id=bundle["id"]
        )
        reg = verificar_idempotencia(parsed["mensaje_id"], parsed["hash_contenido"], 2)
        self.assertIsNotNone(reg)
        self.assertEqual(reg["estado"], "ENTREGADO")

    # 2. Archivo 02: ORU^R01 Laboratorio Sede 1
    def test_02_oru_r01_laboratorio_sede1(self):
        ruta = os.path.join(self.ejemplos_dir, "02_oru_r01_laboratorio_sede1.hl7")
        with open(ruta, "r", encoding="utf-8") as f:
            raw = f.read()

        parsed = parse_hl7_message(raw)
        self.assertEqual(parsed["sede_origen"], 1)
        self.assertEqual(parsed["usuario"]["documento_id"], "1001")
        self.assertEqual(parsed["tipo_mensaje"], "ORU^R01")
        self.assertEqual(len(parsed["tecnologias"]), 1)

        tech = parsed["tecnologias"][0]
        self.assertEqual(tech["loinc_codigo"], "718-7")
        self.assertEqual(tech["valor"], 13.8)
        self.assertEqual(tech["unidad"], "g/dL")

        # Validación
        es_valido, motivos = validar_mensaje_pre_transformacion(parsed)
        self.assertTrue(es_valido, f"El mensaje de laboratorio debería ser válido: {motivos}")

        # Normalización
        bundle = construir_bundle_transaccional(
            usuario=parsed["usuario"],
            atenciones=[parsed["atencion"]],
            tecnologias=parsed["tecnologias"]
        )
        # Debe contener Patient, Encounter y Observation
        tipos = [e["resource"]["resourceType"] for e in bundle["entry"]]
        self.assertIn("Observation", tipos)

    # 3. Archivo 03: ADT^A01 Inválido (Debe ser rechazado con exactamente 3 motivos)
    def test_03_adt_a01_invalido(self):
        ruta = os.path.join(self.ejemplos_dir, "03_adt_a01_invalido.hl7")
        with open(ruta, "r", encoding="utf-8") as f:
            raw = f.read()

        parsed = parse_hl7_message(raw)
        es_valido, motivos = validar_mensaje_pre_transformacion(parsed)

        # Debe ser estrictamente inválido
        self.assertFalse(es_valido)
        self.assertEqual(len(motivos), 3, f"Se esperaban 3 motivos exactos, se obtuvo: {motivos}")

        # Comprobar la presencia de los 3 motivos exigidos por la guía
        motivos_texto = " | ".join(motivos).lower()
        self.assertTrue(any("no numérico" in m.lower() for m in motivos), "Falta motivo: documento no numérico")
        self.assertTrue(any("sexo no válido" in m.lower() for m in motivos), "Falta motivo: sexo no válido")
        self.assertTrue(any("cie-10" in m.lower() for m in motivos), "Falta motivo: diagnóstico sin mapeo a CIE-10")

    # 4. Archivo 04: CSV Legado Sede 3 (3 entregados y 2 rechazados)
    def test_04_sede3_legado_csv(self):
        ruta = os.path.join(self.ejemplos_dir, "04_sede3_legado.csv")
        with open(ruta, "r", encoding="utf-8") as f:
            raw = f.read()

        rows = parse_csv_rows(raw, sede_id=3)
        self.assertEqual(len(rows), 5, "El archivo debe contener exactamente 5 filas")

        entregados = []
        rechazados = []

        for r in rows:
            es_valido, motivos = validar_mensaje_pre_transformacion(r)
            doc = r["usuario"]["documento_id"]
            if es_valido:
                entregados.append(doc)
            else:
                rechazados.append({"doc": doc, "motivos": motivos})

        # Comprobar balance: 3 entregados, 2 rechazados
        self.assertEqual(len(entregados), 3, f"Se esperaban 3 entregados, se obtuvo: {entregados}")
        self.assertEqual(len(rechazados), 2, f"Se esperaban 2 rechazados, se obtuvo: {rechazados}")

        # Documentos entregados: 1008, 1009, 1010
        self.assertListEqual(entregados, ["1008", "1009", "1010"])

        # Documentos rechazados: 1011 (DOLOR MISTERIOSO) y 12 (doc corto de 2 dígitos)
        docs_rechazados = [x["doc"] for x in rechazados]
        self.assertIn("1011", docs_rechazados)
        self.assertIn("12", docs_rechazados)

    # 5. Prueba de Idempotencia: reenvío del mensaje 01 no crea duplicado
    def test_05_idempotencia_reenvio(self):
        ruta = os.path.join(self.ejemplos_dir, "01_adt_a01_valido_sede2.hl7")
        with open(ruta, "r", encoding="utf-8") as f:
            raw = f.read()

        parsed = parse_hl7_message(raw)
        mensaje_id = parsed["mensaje_id"]
        hash_contenido = parsed["hash_contenido"]

        # Primer envío: se registra como ENTREGADO
        registrar_estado_mensaje(
            mensaje_id=mensaje_id,
            formato="HL7_V2",
            sede_id=2,
            tipo_mensaje="ADT_A01",
            estado="ENTREGADO",
            hash_contenido=hash_contenido,
            intentos=1,
            bundle_id="bundle-pac-1007"
        )

        # Segundo envío: verificar idempotencia
        existente = verificar_idempotencia(mensaje_id, hash_contenido, 2)
        self.assertIsNotNone(existente)
        self.assertEqual(existente["estado"], "ENTREGADO")

    # 6. Prueba de Reintentos, Backoff y Dead Letter (Mensaje MUERTO)
    def test_06_reintentos_y_mensaje_muerto(self):
        ruta = os.path.join(self.ejemplos_dir, "02_oru_r01_laboratorio_sede1.hl7")
        with open(ruta, "r", encoding="utf-8") as f:
            raw = f.read()

        parsed = parse_hl7_message(raw)
        bundle = construir_bundle_transaccional(
            usuario=parsed["usuario"],
            atenciones=[parsed["atencion"]],
            tecnologias=parsed["tecnologias"]
        )

        # Simular falla de HAPI FHIR durante 4 intentos
        resultado = procesar_entrega_con_reintentos(
            parsed=parsed,
            bundle=bundle,
            max_intentos=4,
            simular_falla_hapi=True
        )

        self.assertEqual(resultado["estado"], "muerto")
        self.assertEqual(resultado["intentos"], 4)
        self.assertTrue(resultado["puede_reencolar"])

        # Probar reencolar mensaje muerto
        reencole = reencolar_mensaje(parsed["mensaje_id"])
        self.assertEqual(reencole["nuevo_estado"], "REINTENTANDO")


if __name__ == "__main__":
    unittest.main()
