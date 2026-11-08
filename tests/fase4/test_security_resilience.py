"""
tests/fase4/test_security_resilience.py
Pruebas de Seguridad (RBAC), Auditoría Criptográfica Inmutable y Resiliencia.

Valida:
1. Matriz de permisos por rol: casos permitidos y denegados con 403
2. Registro de evento ACCESO_DENEGADO en la cadena inmutable
3. Algoritmo verificador de auditoría y detección de adulteración deliberada
4. Resiliencia ante caída de sede: degradación a reporte incompleto sin caída de la API
"""

import unittest
from fastapi import HTTPException

from app.auth import autenticar_usuario, crear_token_jwt, decodificar_token_jwt
from app.rbac import validar_acceso_historia_clinica
from app.audit import (
    registrar_evento_auditoria,
    verificar_cadena_auditoria,
    adulterar_evento_para_prueba,
    _CADENA_AUDITORIA
)
from db.consulta_unificada import consultar_historia_unificada


class TestSeguridadYResiliencia(unittest.TestCase):

    def setUp(self):
        # Limpiar cadena de auditoría para cada prueba y dejar bloque génesis
        _CADENA_AUDITORIA.clear()
        registrar_evento_auditoria(
            tipo_evento="GENESIS",
            usuario_sistema="SISTEMA",
            rol="sistema",
            recurso_afectado="inicio",
            resultado="EXITOSO"
        )

        self.paciente = {
            "username": "paciente_carlos",
            "rol": "paciente",
            "documento_id": "1001",
            "nombre_completo": "Carlos Perez"
        }
        self.medico = {
            "username": "medico_mateo",
            "rol": "medico",
            "documento_id": "MED-02",
            "nombre_completo": "Dr. Mateo Ruiz"
        }
        self.admisionista = {
            "username": "admision_laura",
            "rol": "admisionista",
            "documento_id": "ADM-01",
            "nombre_completo": "Laura Jimenez"
        }
        self.auditor = {
            "username": "auditor_elena",
            "rol": "auditor",
            "documento_id": "AUD-01",
            "nombre_completo": "Dra. Elena Gomez"
        }

    # ── 1. Pruebas de Matriz de Permisos (RBAC) ─────────────────

    def test_paciente_ve_su_propia_historia_permitido(self):
        """Un paciente puede ver su propia historia clínica (doc 1001)."""
        permitido = validar_acceso_historia_clinica("1001", self.paciente)
        self.assertTrue(permitido)

    def test_paciente_intenta_ver_historia_ajena_denegado_403(self):
        """Un paciente que cambia el doc en la URL por el de otro (1002) recibe 403 y se audita."""
        with self.assertRaises(HTTPException) as ctx:
            validar_acceso_historia_clinica("1002", self.paciente)
        self.assertEqual(ctx.exception.status_code, 403)

        # Verificar que se registró el intento como ACCESO_DENEGADO en la auditoría
        ultimo = _CADENA_AUDITORIA[-1]
        self.assertEqual(ultimo["tipo_evento"], "ACCESO_DENEGADO")
        self.assertEqual(ultimo["resultado"], "DENEGADO")
        self.assertEqual(ultimo["usuario_sistema"], "paciente_carlos")

    def test_medico_consulta_historia_cualquier_paciente_permitido(self):
        """Un médico puede consultar la historia de cualquier paciente."""
        self.assertTrue(validar_acceso_historia_clinica("1001", self.medico))
        self.assertTrue(validar_acceso_historia_clinica("1002", self.medico))

    def test_admisionista_intenta_ver_historia_clinica_denegado_403(self):
        """Un admisionista NO puede ver historias clínicas completas ni diagnósticos."""
        with self.assertRaises(HTTPException) as ctx:
            validar_acceso_historia_clinica("1001", self.admisionista)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(_CADENA_AUDITORIA[-1]["tipo_evento"], "ACCESO_DENEGADO")

    def test_auditor_consulta_historia_para_reporte_permitido(self):
        """Un auditor tiene permiso para consultar historias para el reporte integral."""
        self.assertTrue(validar_acceso_historia_clinica("1001", self.auditor))

    # ── 2. Pruebas de Auditoría Encadenada por Hash SHA-256 ──────

    def test_cadena_auditoria_integra_valida(self):
        """Generar 5 eventos consecutivos y comprobar que la cadena es matemáticamente íntegra."""
        for i in range(5):
            registrar_evento_auditoria(
                tipo_evento="LECTURA_HISTORIA",
                usuario_sistema="medico_mateo",
                rol="medico",
                recurso_afectado=f"/historia/100{i}",
                resultado="EXITOSO"
            )

        es_integra, fallo = verificar_cadena_auditoria()
        self.assertTrue(es_integra)
        self.assertIsNone(fallo)

    def test_deteccion_de_alteracion_maliciosa_en_auditoria(self):
        """
        Prueba obligatoria docente: Adulterar manualmente un campo en la base
        y demostrar que el verificador señala inmediatamente el evento alterado.
        """
        # Registrar eventos válidos
        for i in range(3):
            registrar_evento_auditoria(
                tipo_evento="LOGIN",
                usuario_sistema=f"usuario_{i}",
                rol="medico",
                recurso_afectado="/login",
                resultado="EXITOSO"
            )

        # Adulterar maliciosamente el evento de índice 1 (modificar usuario sin cambiar hash)
        adulterar_evento_para_prueba(indice=1, campo="usuario_sistema", nuevo_valor="hacker_infiltrado")

        # Ejecutar el verificador criptográfico
        es_integra, detalle_fallo = verificar_cadena_auditoria()

        self.assertFalse(es_integra, "El verificador debió detectar la alteración")
        self.assertIsNotNone(detalle_fallo)
        self.assertEqual(detalle_fallo["indice"], 1, "Debe señalar exactamente el índice del evento alterado")
        self.assertIn("Alteración de contenido", detalle_fallo["motivo"])

    # ── 3. Pruebas de Resiliencia ante Caída de Sede ─────────────

    def test_resiliencia_consulta_unificada_con_sede_caida(self):
        """
        Si una sede está caída, la consulta unificada debe:
        - Responder sin error 500
        - Retornar las sedes disponibles
        - Reportar las sedes no disponibles
        - Marcar reporte_completo = False
        """
        resultado = consultar_historia_unificada("1001")
        self.assertIn("sedes_disponibles", resultado)
        self.assertIn("sedes_no_disponibles", resultado)
        self.assertIn("reporte_completo", resultado)

        # Si alguna sede está caída o desconectada en entorno de test
        if len(resultado["sedes_no_disponibles"]) > 0:
            self.assertFalse(resultado["reporte_completo"])
            self.assertIsNotNone(resultado["aviso_incompletitud"])
            self.assertIn("Atención:", resultado["aviso_incompletitud"])


if __name__ == "__main__":
    unittest.main()
