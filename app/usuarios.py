"""
app/usuarios.py
Cuentas de acceso de la plataforma, guardadas en la base central (pg_central.usuario_sistema).

- Contraseñas con PBKDF2-SHA256 (200 000 iteraciones) y sal propia por usuario.
- Quién puede crear qué:
    administrador general (sin sede) -> cualquier rol, cualquier sede
    administrador de sede            -> médico, admisionista y paciente de SU sede
    auditor                          -> solo consulta la lista
- Trazabilidad del registro: origen (SEMILLA, PANEL, ADMISION), creado_por, creado_en, ultimo_acceso.
  Cada alta, cambio de estado o restablecimiento queda además en la auditoría encadenada.
- La cuenta del paciente se crea sola al admitirlo: usuario = documento, contraseña temporal
  que se muestra una vez y que el paciente debe cambiar en su primer ingreso.
- Sin base central (pruebas unitarias) las cuentas viven en memoria.
"""

import os
import re
import hmac
import base64
import hashlib
import secrets
import datetime
import threading
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

USAR_BD = os.getenv("AUDIT_DB_HOST") is not None and PSYCOPG_AVAILABLE
# La API entra a la base central con su propio rol (api_central), no con el superusuario.
CFG = {"host": os.getenv("AUDIT_DB_HOST", "localhost"), "port": int(os.getenv("AUDIT_DB_PORT", "5432")),
       "dbname": os.getenv("AUDIT_DB_NAME", "clinica_central"),
       "user": os.getenv("AUDIT_DB_USER", os.getenv("POSTGRES_USER", "clinica_user")),
       "password": os.getenv("AUDIT_DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", "clinica_pass_2026"))}
ROLES = ("paciente", "admisionista", "medico", "auditor", "administrador")
CAMPOS = ("username", "nombre_completo", "rol", "documento_id", "sede_id", "activo", "debe_cambiar_clave",
          "origen", "creado_por", "creado_en", "ultimo_acceso")

# Cuentas iniciales (datos de prueba, documentadas en el README)
SEMILLA = [
    ("paciente_carlos", "Paciente123!", "paciente", "Carlos Perez", "1001", 1),
    ("admision_laura", "Admision123!", "admisionista", "Laura Jimenez", "ADM-01", 2),
    ("medico_mateo", "Medico123!", "medico", "Dr. Mateo Ruiz", "MED-02", 2),
    ("auditor_elena", "Auditor123!", "auditor", "Dra. Elena Gomez", "AUD-01", None),
    ("admin_plataforma", "Admin123!", "administrador", "Administrador de la plataforma", "ADMIN-01", None),
    ("admin_sincelejo", "Admin123!", "administrador", "Administración IPS Sincelejo Central", "ADMIN-S1", 1),
    ("admin_cartagena", "Admin123!", "administrador", "Administración IPS Cartagena Bocagrande", "ADMIN-S2", 2),
    ("admin_corozal", "Admin123!", "administrador", "Administración IPS Corozal La Perla", "ADMIN-S3", 3),
]

DDL = """
CREATE TABLE IF NOT EXISTS usuario_sistema (
    username            VARCHAR(60) PRIMARY KEY,
    password_hash       VARCHAR(200) NOT NULL,
    rol                 VARCHAR(20)  NOT NULL CHECK (rol IN ('paciente','admisionista','medico','auditor','administrador')),
    nombre_completo     VARCHAR(150) NOT NULL,
    documento_id        VARCHAR(20),
    sede_id             INTEGER CHECK (sede_id IN (1, 2, 3)),
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    debe_cambiar_clave  BOOLEAN NOT NULL DEFAULT FALSE,
    origen              VARCHAR(20)  NOT NULL DEFAULT 'PANEL',
    creado_por          VARCHAR(60),
    creado_en           TIMESTAMP NOT NULL DEFAULT NOW(),
    ultimo_acceso       TIMESTAMP
)"""

_MEMORIA: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()
_INICIALIZADO = False


class ErrorUsuario(Exception):
    def __init__(self, motivos: List[str], status: int = 422):
        super().__init__("; ".join(motivos))
        self.motivos, self.status = motivos, status


# ── Contraseñas ──────────────────────────────────────────────────────────

def hash_clave(clave: str, iteraciones: int = 200_000) -> str:
    sal = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, iteraciones)
    return f"pbkdf2_sha256${iteraciones}${base64.b64encode(sal).decode()}${base64.b64encode(dk).decode()}"


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        _, it, sal, dk = guardado.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), base64.b64decode(sal), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:
        return False


def clave_temporal() -> str:
    """12 caracteres legibles (sin 0/O/1/l) con mayúscula, minúscula, dígito y símbolo."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    base = "".join(secrets.choice(alfabeto) for _ in range(9))
    return base + secrets.choice("23456789") + secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") + secrets.choice("#*-!")


def validar_clave_nueva(clave: str) -> List[str]:
    motivos = []
    if len(clave) < 8:
        motivos.append("la contraseña debe tener al menos 8 caracteres")
    if not re.search(r"[A-Za-z]", clave) or not re.search(r"\d", clave):
        motivos.append("la contraseña debe combinar letras y números")
    return motivos


# ── Almacenamiento ───────────────────────────────────────────────────────

def _conectar():
    from seguridad import tls
    return psycopg2.connect(connect_timeout=3, **CFG, **tls.params_postgres())


def _ahora() -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0)


def _publico(u: Dict[str, Any]) -> Dict[str, Any]:
    salida = {k: u.get(k) for k in CAMPOS}
    for k in ("creado_en", "ultimo_acceso"):
        if isinstance(salida[k], datetime.datetime):
            salida[k] = salida[k].isoformat()
    return salida


def inicializar() -> None:
    """Crea la tabla (si la base central ya existía) y siembra las cuentas iniciales que falten."""
    global _INICIALIZADO
    if _INICIALIZADO:
        return
    with _LOCK:
        if USAR_BD:
            conn = _conectar()
            try:
                with conn, conn.cursor() as cur:
                    # La tabla la crea db/central/init.sql; el rol de la API no tiene permiso de CREATE,
                    # así que solo se intenta si falta (bases antiguas).
                    cur.execute("SELECT to_regclass('public.usuario_sistema') IS NOT NULL")
                    if not cur.fetchone()[0]:
                        cur.execute(DDL)
                    for u, clave, rol, nombre, doc, sede in SEMILLA:
                        cur.execute("""INSERT INTO usuario_sistema (username, password_hash, rol, nombre_completo,
                                           documento_id, sede_id, origen, creado_por)
                                       VALUES (%s,%s,%s,%s,%s,%s,'SEMILLA',NULL) ON CONFLICT (username) DO NOTHING""",
                                    (u, hash_clave(clave), rol, nombre, doc, sede))
            finally:
                conn.close()
        else:
            for u, clave, rol, nombre, doc, sede in SEMILLA:
                _MEMORIA.setdefault(u, {"username": u, "password_hash": hash_clave(clave, 1000), "rol": rol,
                                        "nombre_completo": nombre, "documento_id": doc, "sede_id": sede,
                                        "activo": True, "debe_cambiar_clave": False, "origen": "SEMILLA",
                                        "creado_por": None, "creado_en": _ahora(), "ultimo_acceso": None})
        _INICIALIZADO = True


def _obtener(username: str) -> Optional[Dict[str, Any]]:
    inicializar()
    if not USAR_BD:
        return _MEMORIA.get(username)
    conn = _conectar()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM usuario_sistema WHERE username = %s", (username,))
            fila = cur.fetchone()
            return dict(fila) if fila else None
    finally:
        conn.close()


def _guardar(u: Dict[str, Any], nuevo: bool) -> None:
    if not USAR_BD:
        _MEMORIA[u["username"]] = u
        return
    conn = _conectar()
    try:
        with conn, conn.cursor() as cur:
            if nuevo:
                cur.execute("""INSERT INTO usuario_sistema (username, password_hash, rol, nombre_completo, documento_id,
                                   sede_id, activo, debe_cambiar_clave, origen, creado_por)
                               VALUES (%(username)s, %(password_hash)s, %(rol)s, %(nombre_completo)s, %(documento_id)s,
                                   %(sede_id)s, %(activo)s, %(debe_cambiar_clave)s, %(origen)s, %(creado_por)s)""", u)
            else:
                cur.execute("""UPDATE usuario_sistema SET password_hash=%(password_hash)s, activo=%(activo)s,
                                   debe_cambiar_clave=%(debe_cambiar_clave)s, ultimo_acceso=%(ultimo_acceso)s
                               WHERE username=%(username)s""", u)
    finally:
        conn.close()


# ── Autenticación ────────────────────────────────────────────────────────

def obtener_publico(username: str) -> Optional[Dict[str, Any]]:
    """Datos públicos de una cuenta (sin el hash de la contraseña); None si no existe."""
    u = _obtener(username)
    return _publico(u) if u else None


def autenticar(username: str, clave: str) -> Optional[Dict[str, Any]]:
    u = _obtener((username or "").strip())
    if not u or not u.get("activo") or not verificar_clave(clave or "", u["password_hash"]):
        return None
    u["ultimo_acceso"] = _ahora()
    _guardar(u, nuevo=False)
    return _publico(u)


def cambiar_clave(username: str, actual: str, nueva: str) -> Dict[str, Any]:
    u = _obtener(username)
    if not u or not verificar_clave(actual, u["password_hash"]):
        raise ErrorUsuario(["la contraseña actual no es correcta"])
    motivos = validar_clave_nueva(nueva)
    if actual == nueva:
        motivos.append("la nueva contraseña debe ser distinta de la actual")
    if motivos:
        raise ErrorUsuario(motivos)
    u["password_hash"] = hash_clave(nueva)
    u["debe_cambiar_clave"] = False
    _guardar(u, nuevo=False)
    return _publico(u)


# ── Alcance de gestión ───────────────────────────────────────────────────

def alcance(actor: Dict[str, Any]) -> Dict[str, Any]:
    rol, sede = actor.get("rol"), actor.get("sede_id")
    if rol == "administrador" and not sede:
        return {"puede_gestionar": True, "sedes_gestionables": [1, 2, 3],
                "roles_asignables": ["medico", "admisionista", "paciente", "auditor", "administrador"]}
    if rol == "administrador":
        return {"puede_gestionar": True, "sedes_gestionables": [int(sede)],
                "roles_asignables": ["medico", "admisionista", "paciente"]}
    return {"puede_gestionar": False, "sedes_gestionables": [], "roles_asignables": []}


def _puede_tocar(actor: Dict[str, Any], u: Dict[str, Any]) -> bool:
    a = alcance(actor)
    if not a["puede_gestionar"]:
        return False
    if actor.get("sede_id"):
        return u.get("sede_id") == int(actor["sede_id"]) and u.get("rol") in a["roles_asignables"]
    return True


def listar(actor: Dict[str, Any], texto: Optional[str] = None, rol: Optional[str] = None,
           sede: Optional[int] = None) -> Dict[str, Any]:
    inicializar()
    if USAR_BD:
        conn = _conectar()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM usuario_sistema ORDER BY creado_en DESC, username")
                todos = [dict(f) for f in cur.fetchall()]
        finally:
            conn.close()
    else:
        todos = sorted(_MEMORIA.values(), key=lambda u: str(u["creado_en"]), reverse=True)
    if actor.get("rol") == "administrador" and actor.get("sede_id"):
        todos = [u for u in todos if u.get("sede_id") == int(actor["sede_id"])]
    if texto:
        t = texto.lower()
        todos = [u for u in todos if t in u["username"].lower() or t in (u["nombre_completo"] or "").lower()
                 or t in str(u.get("documento_id") or "").lower()]
    if rol:
        todos = [u for u in todos if u["rol"] == rol]
    if sede:
        todos = [u for u in todos if u.get("sede_id") == int(sede)]
    return {"usuarios": [_publico(u) for u in todos], **alcance(actor)}


# ── Altas y cambios ──────────────────────────────────────────────────────

def crear(datos: Dict[str, Any], actor: Dict[str, Any], origen: str = "PANEL",
          paciente_existe=None) -> Tuple[Dict[str, Any], Optional[str]]:
    """Crea una cuenta. Devuelve (usuario, clave_temporal o None si el actor fijó la clave)."""
    a = alcance(actor)
    if origen == "PANEL" and not a["puede_gestionar"]:
        raise ErrorUsuario(["su rol no puede crear usuarios"], 403)
    username = str(datos.get("username") or "").strip().lower()
    nombre = str(datos.get("nombre_completo") or "").strip()
    rol = str(datos.get("rol") or "").strip()
    doc = str(datos.get("documento_id") or "").strip() or None
    sede = datos.get("sede_id")
    sede = int(sede) if sede not in (None, "", "null") else None
    motivos = []
    if not re.fullmatch(r"[a-z0-9._-]{4,40}", username):
        motivos.append("usuario: de 4 a 40 caracteres (minúsculas, números, punto, guion)")
    if not nombre:
        motivos.append("el nombre es obligatorio")
    if rol not in ROLES:
        motivos.append("rol no válido")
    elif origen == "PANEL" and rol not in a["roles_asignables"]:
        raise ErrorUsuario([f"no puede crear usuarios con rol {rol}"], 403)
    if rol in ("paciente", "medico", "admisionista") and not doc:
        motivos.append("el documento es obligatorio para este rol")
    if rol in ("medico", "admisionista") and sede is None:
        motivos.append("la sede es obligatoria para este rol")
    if origen == "PANEL" and sede is not None and sede not in a["sedes_gestionables"]:
        raise ErrorUsuario([f"no puede crear usuarios de la sede {sede}"], 403)
    if origen == "PANEL" and actor.get("sede_id") and sede != int(actor["sede_id"]):
        raise ErrorUsuario(["solo puede crear usuarios de su propia sede"], 403)
    if rol == "paciente" and doc and paciente_existe and not paciente_existe(doc):
        motivos.append(f"no hay ningún paciente registrado con el documento {doc}")
    clave = str(datos.get("clave") or "")
    if clave:
        motivos += validar_clave_nueva(clave)
    if motivos:
        raise ErrorUsuario(motivos)
    if _obtener(username):
        raise ErrorUsuario([f"el usuario {username} ya existe"], 409)
    temporal = None if clave else clave_temporal()
    u = {"username": username, "password_hash": hash_clave(clave or temporal), "rol": rol, "nombre_completo": nombre,
         "documento_id": doc, "sede_id": sede, "activo": True, "debe_cambiar_clave": not clave,
         "origen": origen, "creado_por": actor.get("username"), "creado_en": _ahora(), "ultimo_acceso": None}
    _guardar(u, nuevo=True)
    return _publico(_obtener(username) or u), temporal


def cambiar_estado(username: str, activo: bool, actor: Dict[str, Any]) -> Dict[str, Any]:
    u = _obtener(username)
    if not u:
        raise ErrorUsuario([f"el usuario {username} no existe"], 404)
    if username == actor.get("username"):
        raise ErrorUsuario(["no puede desactivar su propia cuenta"], 422)
    if not _puede_tocar(actor, u):
        raise ErrorUsuario(["no tiene permiso sobre este usuario"], 403)
    u["activo"] = bool(activo)
    _guardar(u, nuevo=False)
    return _publico(u)


def restablecer(username: str, actor: Dict[str, Any]) -> str:
    u = _obtener(username)
    if not u:
        raise ErrorUsuario([f"el usuario {username} no existe"], 404)
    if not _puede_tocar(actor, u):
        raise ErrorUsuario(["no tiene permiso sobre este usuario"], 403)
    temporal = clave_temporal()
    u["password_hash"] = hash_clave(temporal)
    u["debe_cambiar_clave"] = True
    _guardar(u, nuevo=False)
    return temporal


def cuenta_paciente(documento: str, nombre: str, sede: int, actor: Dict[str, Any]) -> Dict[str, Any]:
    """Cuenta del portal del paciente al admitirlo. Si ya existe, no se toca."""
    username = str(documento).strip()
    existente = _obtener(username)
    if existente:
        return {"username": username, "creada": False, "clave_temporal": None}
    u, temporal = crear({"username": username, "nombre_completo": nombre, "rol": "paciente",
                         "documento_id": username, "sede_id": sede}, actor, origen="ADMISION")
    return {"username": u["username"], "creada": True, "clave_temporal": temporal}
