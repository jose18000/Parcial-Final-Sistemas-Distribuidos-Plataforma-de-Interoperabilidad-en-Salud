"""
tests/fase2/test_traductor_57.py
Traductor universal de los 57 campos: catálogo, esquema, ida y vuelta entre motores.
"""

import re
import unittest

from traductor.catalogo_57 import CAMPOS_57, OBLIGATORIOS, campos_de
from traductor.dominios import normalizar_codigo
from traductor.traductor import (desde_hl7, desde_fila_csv, leer_csv, desde_json, a_postgres, a_mongo,
                                 desde_mongo, cobertura_57, vista_57, calcular_edad)
from hsb.parser_csv import cargar_tabla_terminologia

RUTA_57 = "tests/datos/06_adt_a03_57_campos_sede1.hl7"


def _historia(reg):
    at = dict(reg["atencion"], diagnosticos=reg["diagnosticos"], tecnologias=reg["tecnologias"], egreso=reg["egreso"])
    return reg["usuario"], [at]


class TestCatalogo(unittest.TestCase):

    def test_hay_57_campos_numerados_y_cada_uno_tiene_destino(self):
        self.assertEqual([c.num for c in CAMPOS_57], list(range(1, 58)))
        for c in CAMPOS_57:
            self.assertTrue(c.pg and c.mongo and c.fhir, f"Campo {c.num} sin destino")
        self.assertGreater(len(OBLIGATORIOS), 20)

    def test_schema_sql_tiene_todas_las_columnas_del_catalogo(self):
        sql = open("db/schema.sql", encoding="utf-8").read()
        tablas = dict(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", sql, re.S))
        for cont, tabla in (("usuario", "usuario"), ("atencion", "atencion"), ("tecnologia", "tecnologia_salud"),
                            ("diagnostico", "diagnostico"), ("egreso", "egreso")):
            for c in campos_de(cont):
                col = c.pg.split(".", 1)[1]
                self.assertRegex(tablas[tabla], rf"\n\s+{col}\s", f"Falta {tabla}.{col} (campo {c.num or c.clave})")


class TestTraduccionDeValores(unittest.TestCase):

    def test_sinonimos_de_cada_sede(self):
        self.assertEqual(normalizar_codigo("entorno_atencion", "E"), "01")
        self.assertEqual(normalizar_codigo("clasificacion_triage", "III"), "3")
        self.assertEqual(normalizar_codigo("sexo", "I"), "O")
        self.assertEqual(normalizar_codigo("via_administracion", "PO"), "01")
        self.assertEqual(normalizar_codigo("via_ingreso", "Espontánea"), "01")
        self.assertIsNone(normalizar_codigo("etnia", "MARCIANO"))

    def test_edad_y_unidad(self):
        self.assertEqual(calcular_edad("1990-02-14", "2026-11-07"), (36, "1"))
        self.assertEqual(calcular_edad("2026-08-01", "2026-11-07"), (3, "2"))
        self.assertEqual(calcular_edad("2026-11-01", "2026-11-07"), (6, "3"))


class TestIdaYVuelta(unittest.TestCase):

    def setUp(self):
        _, self.reg = desde_hl7(open(RUTA_57, encoding="utf-8", newline="").read())

    def test_hl7_57_campos_cobertura(self):
        cob = cobertura_57(*_historia(self.reg))
        self.assertEqual(cob["porcentaje_obligatorios"], 100.0)
        self.assertEqual([f["num"] for f in cob["faltantes"]], [42])   # dx de muerte: la paciente egresa viva

    def test_mongo_ida_y_vuelta_conserva_los_57(self):
        antes = vista_57(*[x[0] if isinstance(x, list) else x for x in _historia(self.reg)])
        h = desde_mongo(a_mongo(self.reg))
        despues = vista_57(h["usuario"], h["atenciones"][0])
        self.assertEqual(antes, despues)

    def test_postgres_genera_filas_por_tabla(self):
        filas = a_postgres(self.reg)
        self.assertEqual(filas["usuario"]["documento_id"], "1020")
        self.assertEqual(len(filas["diagnostico"]), 5)
        self.assertEqual({d["rol"] for d in filas["diagnostico"]}, {"INGRESO", "EGRESO", "RELACIONADO"})
        self.assertEqual(filas["egreso"]["codigo_prestador"], "700010000101")

    def test_mongo_fusion_no_borra_datos_previos(self):
        doc = a_mongo(self.reg)
        parcial = desde_json({"usuario": {"documento_id": "1020", "telefono": "3110000000"},
                              "atencion": {"numero_visita": "V-S1-0157"},
                              "tecnologias": [{"tipo": "LABORATORIO", "loinc_codigo": "718-7", "valor": 12}]}, 1)
        h = desde_mongo(a_mongo(parcial, doc))
        self.assertEqual(h["usuario"]["telefono"], "3110000000")
        self.assertEqual(h["usuario"]["ocupacion"], "Enfermera")
        at = h["atenciones"][0]
        self.assertEqual(at["causa_atencion"], "Dolor torácico opresivo de inicio súbito")
        self.assertEqual(len(at["tecnologias"]), 2)

    def test_csv_legado_y_terminologia(self):
        term = cargar_tabla_terminologia("ejemplos/05_ref_terminologia.csv")
        filas = leer_csv(open("ejemplos/04_sede3_legado.csv", encoding="utf-8").read())
        regs = [desde_fila_csv(f, 3, term, l)[1] for f, l in filas]
        self.assertEqual(regs[0]["diagnosticos"][0]["cie10_codigo"], "A09")
        self.assertEqual(regs[0]["usuario"]["apellidos"], "Suarez Pineda")
        self.assertEqual(regs[0]["atencion"]["entorno_atencion"], "01")       # trae triage -> urgencias
        self.assertIn("DOLOR MISTERIOSO", regs[3]["dx_local_error"])

    def test_json_plano_por_numero_de_campo(self):
        reg = desde_json({"2": "5555", "4": "Ana Gil", "5": "2000-01-01", "8": "F", "17": "2026-11-09T08:00",
                          "34": "J45.9"}, 2)
        self.assertEqual(reg["usuario"]["nombre_completo"], "Ana Gil")
        self.assertEqual(reg["diagnosticos"][0]["rol"], "INGRESO")
        self.assertTrue(reg["atencion"]["numero_visita"].startswith("V-S2-5555-"))


if __name__ == "__main__":
    unittest.main()
