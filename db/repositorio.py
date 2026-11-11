"""
db/repositorio.py
Capa de acceso a datos de las sedes con motores HETEROGÉNEOS.

    Sede 1 Sincelejo  -> PostgreSQL  (RepositorioPostgres)
    Sede 2 Cartagena  -> MongoDB     (RepositorioMongo)
    Sede 3 Corozal    -> PostgreSQL  (RepositorioPostgres)

Las dos clases exponen la MISMA interfaz y hablan siempre en el registro canónico del
traductor universal. El bus (HSB), la consulta unificada y el tablero no saben qué
motor tiene cada sede: piden `obtener_repositorio(sede_id)` y listo.

Atomicidad:
  - PostgreSQL: usuario + atención + diagnósticos + tecnologías + egreso en UNA transacción.
  - MongoDB:    la atención completa vive embebida en el documento del paciente, así que
                guardarla es UNA escritura de un solo documento (atómica sin transacciones
                multi-documento ni réplica).
"""

import os
import logging
import datetime
from typing import Any, Dict, List, Optional

from traductor.catalogo_57 import SEDES
from traductor.traductor import a_postgres, desde_postgres, a_mongo, desde_mongo

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG_AVAILABLE = True
except ImportError:  # entorno de pruebas sin driver
    PSYCOPG_AVAILABLE = False

try:
    import pymongo
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False

logger = logging.getLogger("repositorio")

TIMEOUT_S = float(os.getenv("DB_TIMEOUT_SECONDS", "3"))


def marcar_ids_fhir(reg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tras entregar el Bundle a HAPI, el registro queda enlazado a sus recursos FHIR
    (mismos ids deterministas que usa fhir/normalizer.py). Esto es lo que mide la cobertura FHIR.
    """
    doc = reg["usuario"].get("documento_id")
    reg["usuario"]["fhir_patient_id"] = f"pac-{doc}"
    if reg["atencion"].get("numero_visita"):
        reg["atencion"]["fhir_encounter_id"] = f"enc-{reg['atencion']['numero_visita']}"
    for dx in reg["diagnosticos"]:
        dx["fhir_condition_id"] = dx.get("diagnostico_id")
    for t in reg["tecnologias"]:
        t["fhir_resource_id"] = t.get("tecnologia_id")
    return reg


def _json_seguro(fila: Dict[str, Any]) -> Dict[str, Any]:
    salida = {}
    for k, v in fila.items():
        if isinstance(v, (datetime.datetime, datetime.date)):
            v = v.isoformat()
        salida[k] = v
    return salida


class RepositorioSede:
    """Interfaz común de un nodo de sede."""
    motor = "desconocido"

    def __init__(self, sede_id: int):
        self.sede_id = sede_id
        self.nombre = SEDES[sede_id]["nombre"]          # p. ej. "IPS Sincelejo Central"

    # Salud
    def ping(self) -> bool: raise NotImplementedError
    # Historia clínica
    def guardar(self, reg: Dict[str, Any]) -> None: raise NotImplementedError
    def historia(self, documento_id: str) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def cobertura_fhir(self) -> Dict[str, int]: raise NotImplementedError
    # Mensajes del bus
    def buscar_mensaje(self, mensaje_id: str, hash_contenido: str) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def registrar_mensaje(self, msg: Dict[str, Any]) -> None: raise NotImplementedError
    def listar_mensajes(self, limite: int = 50, estado: Optional[str] = None) -> List[Dict[str, Any]]: raise NotImplementedError


# ══════════════════════════════════════════════════════════════════════════
# PostgreSQL
# ══════════════════════════════════════════════════════════════════════════

class RepositorioPostgres(RepositorioSede):
    motor = "postgresql"

    def __init__(self, sede_id: int):
        super().__init__(sede_id)
        n = sede_id
        self.cfg = {
            "host": os.getenv(f"DB_HOST_SEDE{n}", "localhost"),
            "port": int(os.getenv(f"DB_PORT_SEDE{n}", str(5432 + n))),
            "dbname": os.getenv(f"DB_NAME_SEDE{n}", {1: "clinica_sincelejo", 3: "clinica_corozal"}.get(n, "clinica")),
            "user": os.getenv("POSTGRES_USER", "clinica_user"),
            "password": os.getenv("POSTGRES_PASSWORD", "clinica_pass_2026"),
        }

    def _conectar(self):
        if not PSYCOPG_AVAILABLE:
            raise ConnectionError("Driver psycopg2 no instalado")
        return psycopg2.connect(connect_timeout=int(TIMEOUT_S), **self.cfg)

    def ping(self) -> bool:
        try:
            conn = self._conectar()
            conn.close()
            return True
        except Exception:
            return False

    @staticmethod
    def _upsert(cur, tabla: str, fila: Dict[str, Any], pk: str) -> None:
        """INSERT ... ON CONFLICT DO UPDATE sin pisar con NULL lo que ya existía (idempotente)."""
        cols = [c for c, v in fila.items() if v is not None] or [pk]
        if pk not in cols:
            cols.insert(0, pk)
        valores = [fila.get(c) for c in cols]
        actualizar = [c for c in cols if c != pk]
        set_sql = ", ".join(f"{c} = COALESCE(EXCLUDED.{c}, {tabla}.{c})" for c in actualizar) or f"{pk} = EXCLUDED.{pk}"
        sql = (f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
               f"ON CONFLICT ({pk}) DO UPDATE SET {set_sql}")
        cur.execute(sql, valores)

    def guardar(self, reg: Dict[str, Any]) -> None:
        filas = a_postgres(reg)
        conn = self._conectar()
        try:
            with conn:  # una sola transacción: o queda todo o no queda nada
                with conn.cursor() as cur:
                    usuario = dict(filas["usuario"])
                    usuario.setdefault("sede_origen_id", self.sede_id)
                    self._upsert(cur, "usuario", usuario, "documento_id")
                    cur.execute("UPDATE usuario SET actualizado_en = NOW() WHERE documento_id = %s",
                                (usuario["documento_id"],))
                    if filas["atencion"]:
                        at = dict(filas["atencion"])
                        at["sede_id"] = self.sede_id
                        self._upsert(cur, "atencion", at, "numero_visita")
                        for t in filas["tecnologia_salud"]:
                            self._upsert(cur, "tecnologia_salud", t, "tecnologia_id")
                        for dx in filas["diagnostico"]:
                            self._upsert(cur, "diagnostico", dx, "diagnostico_id")
                        if filas["egreso"]:
                            self._upsert(cur, "egreso", filas["egreso"], "numero_visita")
        finally:
            conn.close()

    def historia(self, documento_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conectar()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM usuario WHERE documento_id = %s", (documento_id,))
                usuario = cur.fetchone()
                if not usuario:
                    return None
                cur.execute("SELECT * FROM atencion WHERE documento_id = %s ORDER BY fecha_ingreso DESC",
                            (documento_id,))
                atenciones = cur.fetchall()
                visitas = tuple(a["numero_visita"] for a in atenciones) or ("__ninguna__",)
                cur.execute("SELECT * FROM tecnologia_salud WHERE numero_visita IN %s", (visitas,))
                tecnologias = cur.fetchall()
                cur.execute("SELECT * FROM diagnostico WHERE numero_visita IN %s ORDER BY rol, orden", (visitas,))
                diagnosticos = cur.fetchall()
                cur.execute("SELECT * FROM egreso WHERE numero_visita IN %s", (visitas,))
                egresos = cur.fetchall()
            return desde_postgres(usuario, atenciones, tecnologias, diagnosticos, egresos)
        finally:
            conn.close()

    def cobertura_fhir(self) -> Dict[str, int]:
        conn = self._conectar()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*), COUNT(fhir_patient_id) FROM usuario")
                total, con_fhir = cur.fetchone()
                return {"total_pacientes": total, "pacientes_con_fhir": con_fhir}
        finally:
            conn.close()

    def buscar_mensaje(self, mensaje_id: str, hash_contenido: str) -> Optional[Dict[str, Any]]:
        conn = self._conectar()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM mensaje_bus WHERE mensaje_id = %s OR hash_contenido = %s LIMIT 1",
                            (mensaje_id, hash_contenido))
                fila = cur.fetchone()
                return _json_seguro(dict(fila)) if fila else None
        finally:
            conn.close()

    def registrar_mensaje(self, msg: Dict[str, Any]) -> None:
        conn = self._conectar()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO mensaje_bus (mensaje_id, formato, sede_origen, tipo_mensaje, estado, intentos,
                                             hash_contenido, motivo_rechazo, bundle_id, contenido)
                    VALUES (%(mensaje_id)s, %(formato)s, %(sede_origen)s, %(tipo_mensaje)s, %(estado)s,
                            %(intentos)s, %(hash_contenido)s, %(motivo_rechazo)s, %(bundle_id)s, %(contenido)s)
                    ON CONFLICT (mensaje_id) DO UPDATE SET
                        estado = EXCLUDED.estado, intentos = EXCLUDED.intentos,
                        motivo_rechazo = EXCLUDED.motivo_rechazo,
                        bundle_id = COALESCE(EXCLUDED.bundle_id, mensaje_bus.bundle_id),
                        contenido = COALESCE(EXCLUDED.contenido, mensaje_bus.contenido),
                        actualizado_en = NOW(),
                        entregado_en = CASE WHEN EXCLUDED.estado = 'ENTREGADO' THEN NOW()
                                            ELSE mensaje_bus.entregado_en END
                """, {**{"motivo_rechazo": None, "bundle_id": None, "contenido": None, "intentos": 0}, **msg})
        finally:
            conn.close()

    def listar_mensajes(self, limite: int = 50, estado: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._conectar()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if estado:
                    cur.execute("""SELECT mensaje_id, formato, sede_origen, tipo_mensaje, estado, intentos,
                                   recibido_en, actualizado_en, motivo_rechazo, bundle_id, hash_contenido
                                   FROM mensaje_bus WHERE estado = %s ORDER BY actualizado_en DESC LIMIT %s""",
                                (estado, limite))
                else:
                    cur.execute("""SELECT mensaje_id, formato, sede_origen, tipo_mensaje, estado, intentos,
                                   recibido_en, actualizado_en, motivo_rechazo, bundle_id, hash_contenido
                                   FROM mensaje_bus ORDER BY actualizado_en DESC LIMIT %s""", (limite,))
                return [_json_seguro(dict(f)) for f in cur.fetchall()]
        finally:
            conn.close()

    def listar_pacientes(self, texto: Optional[str] = None, limite: int = 50) -> List[Dict[str, Any]]:
        """Resumen de pacientes de la sede (para el panel), los más recientes primero."""
        conn = self._conectar()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                filtro, params = "", []
                if texto:
                    filtro = "WHERE u.documento_id ILIKE %s OR u.nombre_completo ILIKE %s"
                    params = [f"%{texto}%", f"%{texto}%"]
                cur.execute(f"""
                    SELECT u.documento_id, u.nombre_completo, u.sexo, u.edad, u.unidad_edad,
                           u.municipio_residencia, u.fhir_patient_id,
                           COUNT(a.numero_visita) AS atenciones, MAX(a.fecha_ingreso) AS ultima_atencion,
                           GREATEST(MAX(a.creado_en), MAX(u.actualizado_en)) AS movimiento
                    FROM usuario u LEFT JOIN atencion a ON a.documento_id = u.documento_id
                    {filtro}
                    GROUP BY u.documento_id
                    ORDER BY movimiento DESC NULLS LAST LIMIT %s""", params + [limite])
                return [_json_seguro(dict(f)) for f in cur.fetchall()]
        finally:
            conn.close()

    def contar_por_estado(self) -> Dict[str, int]:
        conn = self._conectar()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT estado, COUNT(*) FROM mensaje_bus GROUP BY estado")
                return {e: n for e, n in cur.fetchall()}
        finally:
            conn.close()

    def obtener_contenido(self, mensaje_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conectar()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM mensaje_bus WHERE mensaje_id = %s", (mensaje_id,))
                fila = cur.fetchone()
                return _json_seguro(dict(fila)) if fila else None
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════════════════════
# MongoDB
# ══════════════════════════════════════════════════════════════════════════

_CLIENTES_MONGO: Dict[str, Any] = {}


class RepositorioMongo(RepositorioSede):
    motor = "mongodb"

    def __init__(self, sede_id: int):
        super().__init__(sede_id)
        n = sede_id
        self.url = os.getenv(f"MONGO_URL_SEDE{n}", "mongodb://localhost:27017")
        self.dbname = os.getenv(f"DB_NAME_SEDE{n}", "clinica_cartagena")

    def _db(self):
        if not PYMONGO_AVAILABLE:
            raise ConnectionError("Driver pymongo no instalado")
        cliente = _CLIENTES_MONGO.get(self.url)
        if cliente is None:
            cliente = pymongo.MongoClient(self.url, serverSelectionTimeoutMS=int(TIMEOUT_S * 1000),
                                          connectTimeoutMS=int(TIMEOUT_S * 1000), tz_aware=False)
            _CLIENTES_MONGO[self.url] = cliente
        return cliente[self.dbname]

    def ping(self) -> bool:
        try:
            self._db().command("ping")
            return True
        except Exception:
            return False

    def guardar(self, reg: Dict[str, Any]) -> None:
        db = self._db()
        doc_id = str(reg["usuario"]["documento_id"])
        existente = db.pacientes.find_one({"_id": doc_id})
        nuevo = a_mongo(reg, existente)
        nuevo.setdefault("sede_origen", self.sede_id)
        for at in nuevo.get("atenciones", []):
            at.setdefault("sede", self.sede_id)
        nuevo["actualizado_en"] = datetime.datetime.utcnow().isoformat(timespec="seconds")
        # Escritura de UN documento: atómica
        db.pacientes.replace_one({"_id": doc_id}, nuevo, upsert=True)

    def historia(self, documento_id: str) -> Optional[Dict[str, Any]]:
        doc = self._db().pacientes.find_one({"_id": str(documento_id)})
        if not doc:
            return None
        hist = desde_mongo(doc)
        hist["atenciones"].sort(key=lambda a: str(a.get("fecha_ingreso") or ""), reverse=True)
        return hist

    def cobertura_fhir(self) -> Dict[str, int]:
        db = self._db()
        total = db.pacientes.count_documents({})
        con_fhir = db.pacientes.count_documents({"fhir_patient_id": {"$nin": [None, ""]}})
        return {"total_pacientes": total, "pacientes_con_fhir": con_fhir}

    def buscar_mensaje(self, mensaje_id: str, hash_contenido: str) -> Optional[Dict[str, Any]]:
        doc = self._db().mensajes_bus.find_one({"$or": [{"_id": mensaje_id}, {"hash_contenido": hash_contenido}]})
        if not doc:
            return None
        doc["mensaje_id"] = doc.pop("_id")
        return doc

    def registrar_mensaje(self, msg: Dict[str, Any]) -> None:
        ahora = datetime.datetime.utcnow().isoformat(timespec="seconds")
        datos = {k: v for k, v in msg.items() if k != "mensaje_id"}
        if datos.get("contenido") is None:
            datos.pop("contenido", None)
        if datos.get("bundle_id") is None:
            datos.pop("bundle_id", None)
        datos["actualizado_en"] = ahora
        if msg.get("estado") == "ENTREGADO":
            datos["entregado_en"] = ahora
        self._db().mensajes_bus.update_one(
            {"_id": msg["mensaje_id"]},
            {"$set": datos, "$setOnInsert": {"recibido_en": ahora}},
            upsert=True,
        )

    def listar_mensajes(self, limite: int = 50, estado: Optional[str] = None) -> List[Dict[str, Any]]:
        filtro = {"estado": estado} if estado else {}
        salida = []
        for d in self._db().mensajes_bus.find(filtro, {"contenido": 0}).sort("actualizado_en", -1).limit(limite):
            d["mensaje_id"] = d.pop("_id")
            salida.append(d)
        return salida

    def listar_pacientes(self, texto: Optional[str] = None, limite: int = 50) -> List[Dict[str, Any]]:
        import re as _re
        filtro: Dict[str, Any] = {}
        if texto:
            patron = {"$regex": _re.escape(texto), "$options": "i"}
            filtro = {"$or": [{"_id": patron}, {"nombre.completo": patron}]}
        salida = []
        cursor = self._db().pacientes.find(filtro, {"nombre": 1, "sexo_biologico": 1, "nacimiento": 1, "residencia": 1,
                                                    "fhir_patient_id": 1, "atenciones.ingreso.fecha": 1,
                                                    "actualizado_en": 1})
        for d in cursor.sort("actualizado_en", -1).limit(limite):
            fechas = [a.get("ingreso", {}).get("fecha") for a in d.get("atenciones", []) if a.get("ingreso", {}).get("fecha")]
            salida.append({
                "documento_id": d["_id"], "nombre_completo": (d.get("nombre") or {}).get("completo"),
                "sexo": d.get("sexo_biologico"), "edad": (d.get("nacimiento") or {}).get("edad"),
                "unidad_edad": (d.get("nacimiento") or {}).get("unidad_edad"),
                "municipio_residencia": (d.get("residencia") or {}).get("municipio_dane"),
                "fhir_patient_id": d.get("fhir_patient_id"), "atenciones": len(d.get("atenciones", [])),
                "ultima_atencion": max(fechas) if fechas else None, "movimiento": d.get("actualizado_en")})
        return salida

    def contar_por_estado(self) -> Dict[str, int]:
        return {r["_id"]: r["n"] for r in self._db().mensajes_bus.aggregate(
            [{"$group": {"_id": "$estado", "n": {"$sum": 1}}}])}

    def obtener_contenido(self, mensaje_id: str) -> Optional[Dict[str, Any]]:
        d = self._db().mensajes_bus.find_one({"_id": mensaje_id})
        if d:
            d["mensaje_id"] = d.pop("_id")
        return d


# ══════════════════════════════════════════════════════════════════════════
# Fábrica
# ══════════════════════════════════════════════════════════════════════════

_REPOS: Dict[int, RepositorioSede] = {}


def obtener_repositorio(sede_id: int) -> RepositorioSede:
    """Devuelve el repositorio de la sede según su motor (catálogo SEDES, sobreescribible con SEDE<n>_MOTOR)."""
    sede_id = int(sede_id)
    if sede_id not in SEDES:
        raise ValueError(f"Sede desconocida: {sede_id}")
    if sede_id not in _REPOS:
        motor = os.getenv(f"SEDE{sede_id}_MOTOR", SEDES[sede_id]["motor"]).lower()
        _REPOS[sede_id] = RepositorioMongo(sede_id) if motor.startswith("mongo") else RepositorioPostgres(sede_id)
    return _REPOS[sede_id]


def todos_los_repositorios() -> List[RepositorioSede]:
    return [obtener_repositorio(s) for s in sorted(SEDES)]
