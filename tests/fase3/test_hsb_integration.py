"""
tests/fase3/test_hsb_integration.py
Integración del HSB con los ejemplos oficiales (ejemplos/LEEME.md), sin Docker:
las sedes se reemplazan por repositorios en memoria (uno con forma Mongo, dos con forma
relacional, como en la red real) y HAPI por un doble que puede "caerse".
"""

import time
import unittest
from unittest import mock

import db.repositorio as repositorio
from db.repositorio import RepositorioSede
from traductor.traductor import a_mongo, desde_mongo, desde_hl7
from hsb import queue_manager
from hsb.ingesta import procesar, contenido_csv
from hsb.parser_csv import parse_csv_rows


class RepoMemoria(RepositorioSede):
    """Sede en memoria. Guarda las historias con el traductor Mongo (documento por paciente)."""

    def __init__(self, sede_id, motor):
        super().__init__(sede_id)
        self.motor = motor
        self.pacientes, self.mensajes, self.caida, self.escrituras = {}, {}, False, 0

    def _ok(self):
        if self.caida:
            raise ConnectionError(f"sede {self.sede_id} apagada")

    def ping(self):
        return not self.caida

    def guardar(self, reg):
        self._ok()
        self.escrituras += 1
        doc = reg["usuario"]["documento_id"]
        self.pacientes[doc] = a_mongo(reg, self.pacientes.get(doc))

    def historia(self, documento_id):
        self._ok()
        return desde_mongo(self.pacientes[documento_id]) if documento_id in self.pacientes else None

    def cobertura_fhir(self):
        self._ok()
        return {"total_pacientes": len(self.pacientes),
                "pacientes_con_fhir": sum(1 for p in self.pacientes.values() if p.get("fhir_patient_id"))}

    def buscar_mensaje(self, mensaje_id, hash_contenido):
        self._ok()
        return self.mensajes.get(mensaje_id) or next(
            (m for m in self.mensajes.values() if m["hash_contenido"] == hash_contenido), None)

    def registrar_mensaje(self, msg):
        self._ok()
        previo = self.mensajes.get(msg["mensaje_id"], {})
        self.mensajes[msg["mensaje_id"]] = {**previo, **{k: v for k, v in msg.items() if v is not None},
                                           "estado": msg["estado"], "intentos": msg["intentos"],
                                           "actualizado_en": time.time()}

    def listar_mensajes(self, limite=50, estado=None):
        self._ok()
        return [m for m in self.mensajes.values() if not estado or m["estado"] == estado][:limite]

    def contar_por_estado(self):
        cuenta = {}
        for m in self.mensajes.values():
            cuenta[m["estado"]] = cuenta.get(m["estado"], 0) + 1
        return cuenta

    def obtener_contenido(self, mensaje_id):
        self._ok()
        return self.mensajes.get(mensaje_id)


def leer(nombre):
    with open(f"ejemplos/{nombre}", encoding="utf-8", newline="") as f:
        return f.read()


class TestHSB(unittest.TestCase):

    def setUp(self):
        self.repos = {1: RepoMemoria(1, "postgresql"), 2: RepoMemoria(2, "mongodb"), 3: RepoMemoria(3, "postgresql")}
        repositorio._REPOS.clear()
        repositorio._REPOS.update(self.repos)
        queue_manager._MEMORIA_MENSAJES.clear()
        self.hapi_arriba = True
        self.bundles = []
        parche = mock.patch.object(queue_manager, "enviar_bundle_a_hapi", side_effect=self._hapi)
        parche.start()
        self.addCleanup(parche.stop)
        programar = mock.patch.object(queue_manager.COLA, "programar")   # sin hilo en las pruebas
        self.programados = programar.start()
        self.addCleanup(programar.stop)

    def tearDown(self):
        repositorio._REPOS.clear()

    def _hapi(self, bundle, timeout_sec=8.0):
        if not self.hapi_arriba:
            return False, "HAPI FHIR no disponible: ConnectError"
        self.bundles.append(bundle)
        return True, "ok"

    def _hl7(self, nombre):
        raw = leer(nombre)
        meta, reg = desde_hl7(raw)
        return procesar(meta, reg, raw.strip())

    def _csv(self, nombre, sede):
        salida = []
        for f in parse_csv_rows(leer(nombre), sede):
            reg = {k: f[k] for k in ("usuario", "atencion", "tecnologias", "diagnosticos", "egreso", "_observaciones")}
            if f.get("dx_local_error"):
                reg["dx_local_error"] = f["dx_local_error"]
            meta = {k: f[k] for k in ("formato", "mensaje_id", "tipo_mensaje", "sede_origen", "sede_raw", "hash_contenido")}
            salida.append(procesar(meta, reg, contenido_csv(f["encabezado"], f["linea"])))
        return salida

    # 01: Patient 1007, Encounter y Condition J45.9 en la sede 2 (MongoDB)
    def test_01_adt_valido_llega_a_la_sede_2(self):
        r = self._hl7("01_adt_a01_valido_sede2.hl7")
        self.assertEqual(r["estado"], "entregado")
        self.assertIn("Patient/pac-1007", r["recursos_fhir"])
        self.assertIn("Condition/cond-V-S2-0101-ing-J45.9", r["recursos_fhir"])
        h = self.repos[2].historia("1007")
        self.assertEqual(h["atenciones"][0]["diagnosticos"][0]["cie10_codigo"], "J45.9")
        self.assertEqual(h["usuario"]["fhir_patient_id"], "pac-1007")
        self.assertIsNone(self.repos[1].historia("1007"))

    # 02: Observation LOINC 718-7 = 13,8 g/dL del paciente 1001 en la sede 1
    def test_02_oru_laboratorio_sede_1(self):
        r = self._hl7("02_oru_r01_laboratorio_sede1.hl7")
        self.assertEqual(r["estado"], "entregado")
        obs = [e["resource"] for e in self.bundles[0]["entry"] if e["resource"]["resourceType"] == "Observation"][0]
        self.assertEqual(obs["code"]["coding"][0]["code"], "718-7")
        self.assertEqual(obs["valueQuantity"]["value"], 13.8)
        self.assertEqual(obs["valueQuantity"]["unit"], "g/dL")
        self.assertIn("1001", self.repos[1].pacientes)

    # 03: rechazado con 3 motivos
    def test_03_adt_invalido_tres_motivos(self):
        r = self._hl7("03_adt_a01_invalido.hl7")
        self.assertEqual(r["estado"], "rechazado")
        self.assertEqual(r["total_motivos"], 3)
        texto = " | ".join(r["motivos"])
        for m in ("documento no numérico", "sexo no válido", "diagnóstico sin mapeo a CIE-10"):
            self.assertIn(m, texto)
        self.assertEqual(self.repos[3].mensajes["MSG-0003"]["estado"], "RECHAZADO")   # no se pierde en silencio
        self.assertEqual(self.bundles, [])

    # 04: 3 entregados (1008, 1009, 1010) y 2 rechazados
    def test_04_csv_legado_sede_3(self):
        res = self._csv("04_sede3_legado.csv", 3)
        entregados = [r["documento"] for r in res if r["estado"] == "entregado"]
        rechazados = [r for r in res if r["estado"] == "rechazado"]
        self.assertEqual(entregados, ["1008", "1009", "1010"])
        self.assertEqual(len(rechazados), 2)
        motivos = " | ".join(m for r in rechazados for m in r["motivos"])
        self.assertIn("sin mapeo a CIE-10", motivos)
        self.assertIn("2 dígitos", motivos)

    # Reenviar 01: la segunda vez es duplicado y hay un solo paciente 1007
    def test_05_idempotencia(self):
        self.assertEqual(self._hl7("01_adt_a01_valido_sede2.hl7")["estado"], "entregado")
        segundo = self._hl7("01_adt_a01_valido_sede2.hl7")
        self.assertEqual(segundo["estado"], "duplicado")
        self.assertEqual(self.repos[2].escrituras, 1)
        self.assertEqual(len(self.repos[2].historia("1007")["atenciones"]), 1)

    # Reenviar el CSV: todas las filas válidas son duplicadas
    def test_06_idempotencia_csv(self):
        self._csv("04_sede3_legado.csv", 3)
        segunda = self._csv("04_sede3_legado.csv", 3)
        self.assertEqual([r["estado"] for r in segunda].count("duplicado"), 3)

    # HAPI caído: REINTENTANDO; cuando vuelve, el reintento entrega sin duplicar
    def test_07_reintento_y_entrega_al_volver_hapi(self):
        self.hapi_arriba = False
        r = self._hl7("02_oru_r01_laboratorio_sede1.hl7")
        self.assertEqual(r["estado"], "reintentando")
        self.assertEqual(self.repos[1].mensajes["MSG-0002"]["estado"], "REINTENTANDO")
        trabajo = self.programados.call_args[0][0]
        self.hapi_arriba = True
        queue_manager._reintentar(trabajo)
        self.assertEqual(self.repos[1].mensajes["MSG-0002"]["estado"], "ENTREGADO")
        self.assertEqual(self.repos[1].escrituras, 1)
        self.assertEqual(self._hl7("02_oru_r01_laboratorio_sede1.hl7")["estado"], "duplicado")

    # HAPI caído más intentos que el máximo: MUERTO, y se puede reencolar
    def test_08_mensaje_muerto_y_reencolar(self):
        self.hapi_arriba = False
        self._hl7("02_oru_r01_laboratorio_sede1.hl7")
        trabajo = self.programados.call_args[0][0]
        while self.repos[1].mensajes["MSG-0002"]["estado"] != "MUERTO":
            queue_manager._reintentar(trabajo)
        self.assertEqual(self.repos[1].mensajes["MSG-0002"]["intentos"], queue_manager.MAX_REINTENTOS)
        self.hapi_arriba = True
        self.assertEqual(queue_manager.reencolar_mensaje("MSG-0002")["nuevo_estado"], "REINTENTANDO")
        queue_manager._reintentar(self.programados.call_args[0][0])
        self.assertEqual(self.repos[1].mensajes["MSG-0002"]["estado"], "ENTREGADO")

    # Error de datos en la sede: no se reintenta, va directo a MUERTO con su motivo
    def test_10_error_de_datos_no_se_reintenta(self):
        class IntegrityError(Exception):
            pass
        with mock.patch.object(self.repos[1], "guardar", side_effect=IntegrityError("null value in column x")):
            r = self._hl7("02_oru_r01_laboratorio_sede1.hl7")
        self.assertEqual(r["estado"], "muerto")
        self.assertEqual(self.repos[1].mensajes["MSG-0002"]["estado"], "MUERTO")
        self.assertIn("rechazó los datos", self.repos[1].mensajes["MSG-0002"]["motivo_rechazo"])
        self.programados.assert_not_called()

    # Un ORU parcial no borra en FHIR lo que la atención ya tenía (el Bundle se completa con la sede)
    def test_11_mensaje_parcial_no_pierde_datos_en_fhir(self):
        self._hl7("01_adt_a01_valido_sede2.hl7")
        oru = ("MSH|^~\\&|LAB|SEDE2|HSB|CENTRAL|20261107120000||ORU^R01|MSG-LAB-1007|P|2.5\r"
               "PID|1||1007^^^HIS||Rojas^Andrea||19900214|F\r"
               "PV1|1|O|||||MED-02^Ruiz^Mateo||||||||||||V-S2-0101|||||||||||||||||||||||||202611071015\r"
               "OBX|1|NM|718-7^Hemoglobina^LN||12.9|g/dL|||||F\r")
        meta, reg = desde_hl7(oru)
        self.assertEqual(procesar(meta, reg, oru)["estado"], "entregado")
        ultimo = self.bundles[-1]
        enc = next(e["resource"] for e in ultimo["entry"] if e["resource"]["resourceType"] == "Encounter")
        self.assertEqual([d["use"]["coding"][0]["code"] for d in enc["diagnosis"]], ["AD"])
        tipos = [e["resource"]["resourceType"] for e in ultimo["entry"]]
        self.assertIn("Condition", tipos)
        self.assertIn("Observation", tipos)

    # Sede caída: el bus reintenta; HAPI primero, la sede después (PUT idempotente)
    def test_09_sede_caida_se_entrega_al_volver(self):
        self.repos[2].caida = True
        r = self._hl7("01_adt_a01_valido_sede2.hl7")
        self.assertEqual(r["estado"], "reintentando")
        self.repos[2].caida = False
        queue_manager._reintentar(self.programados.call_args[0][0])
        self.assertIn("1007", self.repos[2].pacientes)
        self.assertEqual(len(self.bundles), 2)   # HAPI recibió el mismo Bundle dos veces: PUT, sin duplicar


if __name__ == "__main__":
    unittest.main()
