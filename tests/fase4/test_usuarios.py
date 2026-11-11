"""
tests/fase4/test_usuarios.py
Gestión de cuentas: alcance por rol y sede, contraseñas temporales y cuenta del paciente.
(Sin base central: las cuentas viven en memoria.)
"""

import unittest

from app import usuarios as U

ADMIN = {"username": "admin_plataforma", "rol": "administrador", "sede_id": None}
ADMIN_S2 = {"username": "admin_cartagena", "rol": "administrador", "sede_id": 2}
AUDITOR = {"username": "auditor_elena", "rol": "auditor", "sede_id": None}


class TestUsuarios(unittest.TestCase):

    def setUp(self):
        U._MEMORIA.clear()
        U._INICIALIZADO = False
        U.inicializar()

    def test_semilla_y_login(self):
        self.assertIsNotNone(U.autenticar("medico_mateo", "Medico123!"))
        self.assertIsNone(U.autenticar("medico_mateo", "otra"))
        self.assertTrue(U._MEMORIA["admin_plataforma"]["password_hash"].startswith("pbkdf2_sha256$"))

    def test_admin_de_sede_solo_crea_en_su_sede(self):
        u, temporal = U.crear({"username": "med.nuevo", "nombre_completo": "Dra. Nueva", "rol": "medico",
                               "documento_id": "MED-09", "sede_id": 2}, ADMIN_S2)
        self.assertEqual((u["sede_id"], u["origen"], u["creado_por"]), (2, "PANEL", "admin_cartagena"))
        self.assertTrue(temporal and u["debe_cambiar_clave"])
        with self.assertRaises(U.ErrorUsuario) as ctx:
            U.crear({"username": "med.otro", "nombre_completo": "X", "rol": "medico", "documento_id": "M1",
                     "sede_id": 1}, ADMIN_S2)
        self.assertEqual(ctx.exception.status, 403)
        with self.assertRaises(U.ErrorUsuario):
            U.crear({"username": "otro.admin", "nombre_completo": "X", "rol": "administrador", "sede_id": 2}, ADMIN_S2)

    def test_auditor_no_gestiona_y_admin_de_sede_ve_solo_su_sede(self):
        with self.assertRaises(U.ErrorUsuario) as ctx:
            U.crear({"username": "x.x.x", "nombre_completo": "X", "rol": "medico", "documento_id": "1",
                     "sede_id": 1}, AUDITOR)
        self.assertEqual(ctx.exception.status, 403)
        self.assertFalse(U.listar(AUDITOR)["puede_gestionar"])
        self.assertTrue(all(u["sede_id"] == 2 for u in U.listar(ADMIN_S2)["usuarios"]))

    def test_paciente_debe_existir(self):
        with self.assertRaises(U.ErrorUsuario):
            U.crear({"username": "9999", "nombre_completo": "Nadie", "rol": "paciente", "documento_id": "9999",
                     "sede_id": 1}, ADMIN, paciente_existe=lambda d: False)

    def test_clave_temporal_y_cambio_obligatorio(self):
        _, temporal = U.crear({"username": "adm.sede1", "nombre_completo": "Admisión", "rol": "admisionista",
                               "documento_id": "ADM-9", "sede_id": 1}, ADMIN)
        u = U.autenticar("adm.sede1", temporal)
        self.assertTrue(u["debe_cambiar_clave"])
        U.cambiar_clave("adm.sede1", temporal, "NuevaClave2026")
        self.assertFalse(U.autenticar("adm.sede1", "NuevaClave2026")["debe_cambiar_clave"])

    def test_desactivar_impide_el_ingreso(self):
        U.cambiar_estado("medico_mateo", False, ADMIN)
        self.assertIsNone(U.autenticar("medico_mateo", "Medico123!"))
        with self.assertRaises(U.ErrorUsuario):
            U.cambiar_estado("admin_plataforma", False, ADMIN)   # no puede desactivarse a sí mismo

    def test_cuenta_del_paciente_al_admitir(self):
        c = U.cuenta_paciente("52001234", "Rosa Diaz", 3, {"username": "admision_laura", "rol": "admisionista"})
        self.assertTrue(c["creada"] and c["clave_temporal"])
        self.assertEqual(U._MEMORIA["52001234"]["origen"], "ADMISION")
        self.assertFalse(U.cuenta_paciente("52001234", "Rosa Diaz", 3, {"username": "x", "rol": "admisionista"})["creada"])


if __name__ == "__main__":
    unittest.main()
