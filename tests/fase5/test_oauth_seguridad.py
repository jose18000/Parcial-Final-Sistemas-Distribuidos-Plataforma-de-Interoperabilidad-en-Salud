"""
tests/fase5/test_oauth_seguridad.py
Servidor OAuth 2.0 de la API y autorización del HSB (sin bases ni red: todo en memoria).
"""

import base64
import unittest

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import oauth
from app.main import app as api
from hsb import autorizacion
from seguridad.tokens import ValidadorJWT, TokenInvalido


def basic(cid: str, sec: str) -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode()}


PORTAL = basic("portal_web", oauth.CLIENTES["portal_web"]["secreto"])
QA = basic("herramientas_qa", oauth.CLIENTES["herramientas_qa"]["secreto"])
SEDE1 = basic("sistema_sede1", oauth.CLIENTES["sistema_sede1"]["secreto"])


class TestServidorOAuth(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(api)

    def token(self, datos, cab):
        return self.c.post("/oauth/token", data=datos, headers=cab)

    def test_password_grant_emite_token_rs256_con_scopes_del_rol(self):
        r = self.token({"grant_type": "password", "username": "medico_mateo", "password": "Medico123!"}, PORTAL)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["token_type"], "Bearer")
        self.assertIn("refresh_token", d)
        self.assertEqual(r.headers.get("cache-control"), "no-store")
        claims = oauth.verificar(d["access_token"], "api")
        self.assertEqual(claims["rol"], "medico")
        self.assertIn("historia.escribir", claims["scope"].split())
        self.assertEqual(claims["iss"], oauth.ISSUER)

    def test_secreto_de_cliente_incorrecto_401_invalid_client(self):
        r = self.token({"grant_type": "password", "username": "medico_mateo", "password": "Medico123!"},
                       basic("portal_web", "otro"))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "invalid_client")
        self.assertIn("Basic", r.headers.get("www-authenticate", ""))

    def test_contrasena_incorrecta_400_invalid_grant(self):
        r = self.token({"grant_type": "password", "username": "medico_mateo", "password": "mala"}, PORTAL)
        self.assertEqual((r.status_code, r.json()["error"]), (400, "invalid_grant"))

    def test_grant_no_soportado_y_cliente_no_autorizado(self):
        self.assertEqual(self.token({"grant_type": "implicit"}, PORTAL).json()["error"], "unsupported_grant_type")
        self.assertEqual(self.token({"grant_type": "client_credentials"}, PORTAL).json()["error"], "unauthorized_client")

    def test_scope_fuera_del_rol_invalid_scope(self):
        r = self.token({"grant_type": "password", "username": "paciente_carlos", "password": "Paciente123!",
                        "scope": "historia.leer"}, PORTAL)
        self.assertEqual(r.json()["error"], "invalid_scope")

    def test_client_credentials_de_sede_lleva_sede_y_audiencia_hsb(self):
        d = self.token({"grant_type": "client_credentials"}, SEDE1).json()
        claims = oauth.verificar(d["access_token"], "hsb")
        self.assertEqual((claims["sede_id"], claims["scope"]), (1, "hsb.ingesta"))
        with self.assertRaises(Exception):
            oauth.verificar(d["access_token"], "api")     # un token de servicio no sirve para la API

    def test_refresh_token_rota_y_el_viejo_queda_invalido(self):
        d = self.token({"grant_type": "password", "username": "auditor_elena", "password": "Auditor123!"}, PORTAL).json()
        r1 = self.token({"grant_type": "refresh_token", "refresh_token": d["refresh_token"]}, PORTAL)
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertNotEqual(r1.json()["refresh_token"], d["refresh_token"])
        r2 = self.token({"grant_type": "refresh_token", "refresh_token": d["refresh_token"]}, PORTAL)
        self.assertEqual(r2.json()["error"], "invalid_grant")

    def test_revocacion_e_introspeccion(self):
        d = self.token({"grant_type": "password", "username": "auditor_elena", "password": "Auditor123!"}, PORTAL).json()
        i = self.c.post("/oauth/introspect", data={"token": d["access_token"]}, headers=PORTAL).json()
        self.assertTrue(i["active"])
        self.assertEqual(i["username"], "auditor_elena")
        self.assertEqual(self.c.post("/oauth/revoke", data={"token": d["refresh_token"]}, headers=PORTAL).status_code, 200)
        self.assertFalse(self.c.post("/oauth/introspect", data={"token": d["refresh_token"]}, headers=PORTAL).json()["active"])
        self.assertFalse(self.c.post("/oauth/introspect", data={"token": "basura"}, headers=PORTAL).json()["active"])

    def test_jwks_y_metadatos(self):
        jwk = self.c.get("/oauth/jwks").json()["keys"][0]
        self.assertEqual((jwk["kty"], jwk["alg"]), ("RSA", "RS256"))
        meta = self.c.get("/.well-known/oauth-authorization-server").json()
        self.assertIn("client_credentials", meta["grant_types_supported"])
        self.assertTrue(meta["token_endpoint"].endswith("/oauth/token"))

    def test_api_rechaza_token_de_servicio_y_acepta_bearer_de_usuario(self):
        servicio = self.token({"grant_type": "client_credentials"}, QA).json()["access_token"]
        r = self.c.get("/api/catalogo-57", headers={"Authorization": f"Bearer {servicio}"})
        self.assertEqual(r.status_code, 401)
        usuario = self.token({"grant_type": "password", "username": "medico_mateo", "password": "Medico123!"},
                             QA).json()["access_token"]
        r = self.c.get("/api/catalogo-57", headers={"Authorization": f"Bearer {usuario}"})
        self.assertEqual(r.status_code, 200)


class TestAutorizacionHSB(unittest.TestCase):
    """El bus valida el token con la clave pública, sin secretos compartidos."""

    def setUp(self):
        self._antes = (autorizacion.REQUIERE_TOKEN, autorizacion.VALIDADOR)
        autorizacion.REQUIERE_TOKEN = True
        autorizacion.VALIDADOR = ValidadorJWT(clave_publica_pem=oauth._claves()["publica_pem"], audiencia="hsb")
        mini = FastAPI()

        @mini.post("/ingesta")
        def ingesta(sede: int, claims=Depends(autorizacion.requerir("hsb.ingesta"))):
            autorizacion.verificar_sede(claims, sede)
            return {"ok": True, "cliente": claims["client_id"]}

        @mini.post("/admin", dependencies=[Depends(autorizacion.requerir("hsb.admin"))])
        def admin():
            return {"ok": True}

        self.c = TestClient(mini)

    def tearDown(self):
        autorizacion.REQUIERE_TOKEN, autorizacion.VALIDADOR = self._antes

    def bearer(self, cliente):
        tok = oauth.token_de_servicio({"client_id": cliente, **oauth.CLIENTES[cliente]})["access_token"]
        return {"Authorization": f"Bearer {tok}"}

    def test_sin_token_401_con_www_authenticate(self):
        r = self.c.post("/ingesta?sede=1")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Bearer", r.headers["www-authenticate"])

    def test_token_de_usuario_no_sirve_en_el_bus(self):
        tok = oauth.token_de_usuario({"username": "medico_mateo", "rol": "medico"})["access_token"]
        self.assertEqual(self.c.post("/ingesta?sede=1", headers={"Authorization": f"Bearer {tok}"}).status_code, 401)

    def test_sistema_de_sede_solo_escribe_en_su_sede(self):
        self.assertEqual(self.c.post("/ingesta?sede=1", headers=self.bearer("sistema_sede1")).status_code, 200)
        r = self.c.post("/ingesta?sede=3", headers=self.bearer("sistema_sede1"))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["error"], "insufficient_scope")

    def test_scope_admin_requerido(self):
        self.assertEqual(self.c.post("/admin", headers=self.bearer("sistema_sede2")).status_code, 403)
        self.assertEqual(self.c.post("/admin", headers=self.bearer("api_gateway")).status_code, 200)

    def test_token_alterado_rechazado(self):
        tok = self.bearer("api_gateway")["Authorization"]
        cab, cuerpo, firma = tok[7:].split(".")
        alterado = f"Bearer {cab}.{cuerpo}.{firma[:-4]}AAAA"
        self.assertEqual(self.c.post("/admin", headers={"Authorization": alterado}).status_code, 401)

    def test_validador_rechaza_token_vencido(self):
        tok, _ = oauth.firmar({"sub": "x", "aud": ["hsb"], "scope": "hsb.admin"}, minutos=-1)
        with self.assertRaises(TokenInvalido):
            autorizacion.VALIDADOR.validar(tok, ["hsb.admin"])


if __name__ == "__main__":
    unittest.main()
