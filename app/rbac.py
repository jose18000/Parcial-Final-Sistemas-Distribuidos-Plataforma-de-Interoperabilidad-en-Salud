"""
app/rbac.py
Control de Acceso Basado en Roles (RBAC) y Matriz de Permisos.

Matriz oficial de permisos:
Acción                         | Paciente | Admisionista | Médico | Auditor
-------------------------------|----------|--------------|--------|--------
Ver su propia historia         | Sí       | No           | No     | No
Ver la historia de otro pac.   | No       | No           | Sí     | Sí (rep)
Abrir una atención             | No       | Sí           | No     | No
Registrar diagnóstico o egreso | No       | No           | Sí     | No
Ver el estado de la plataforma | No       | No           | Sí     | Sí
Apagar / encender nodo (demo)  | No       | No           | No     | Sí
"""

from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth import decodificar_token_jwt
from app.audit import registrar_evento_auditoria

security = HTTPBearer(auto_error=False)


def obtener_usuario_autenticado(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    request: Request = None
) -> Dict[str, Any]:
    """Extrae el usuario autenticado a partir del header Bearer token o de una cookie de sesión."""
    token = None
    if credentials:
        token = credentials.credentials
    elif request and "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Proporcione un token JWT válido.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = decodificar_token_jwt(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return payload


def requerir_roles(roles_permitidos: List[str]):
    """Dependencia FastAPI que restringe el acceso a un conjunto de roles específicos."""
    def _verificar(usuario: Dict[str, Any] = Depends(obtener_usuario_autenticado), request: Request = None):
        rol = usuario.get("rol")
        username = usuario.get("username", "desconocido")

        if rol not in roles_permitidos:
            recurso = request.url.path if request else "recurso_protegido"
            # Registrar acceso denegado en la auditoría inmutable
            registrar_evento_auditoria(
                tipo_evento="ACCESO_DENEGADO",
                usuario_sistema=username,
                rol=rol or "anonimo",
                recurso_afectado=recurso,
                resultado="DENEGADO",
                detalle={"motivo": f"Rol '{rol}' no autorizado. Se requieren: {roles_permitidos}"}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: El rol '{rol}' no tiene permisos para realizar esta acción."
            )
        return usuario
    return _verificar


def validar_acceso_historia_clinica(documento_objetivo: str, usuario: Dict[str, Any], request: Request = None) -> bool:
    """
    Verifica si el usuario puede acceder a la historia clínica del documento especificado:
    - Paciente: SÓLO si su documento coincide exactamente con el solicitado.
    - Médico y Auditor: Acceso permitido.
    - Admisionista: DENEGADO (principio de mínimo privilegio).
    """
    rol = usuario.get("rol")
    doc_usuario = str(usuario.get("documento_id", "")).strip()
    doc_target = str(documento_objetivo).strip()
    username = usuario.get("username", "desconocido")

    # Regla Paciente
    if rol == "paciente":
        if doc_usuario == doc_target:
            return True
        else:
            # Intento de ver la historia de otro paciente
            registrar_evento_auditoria(
                tipo_evento="ACCESO_DENEGADO",
                usuario_sistema=username,
                rol=rol,
                recurso_afectado=f"/historia/{doc_target}",
                resultado="DENEGADO",
                detalle={"motivo": f"Paciente {doc_usuario} intentó acceder a historia ajena {doc_target}"}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado: Un paciente sólo puede consultar su propia historia clínica."
            )

    # Regla Médico y Auditor
    if rol in ("medico", "auditor"):
        return True

    # Regla Admisionista
    registrar_evento_auditoria(
        tipo_evento="ACCESO_DENEGADO",
        usuario_sistema=username,
        rol=rol,
        recurso_afectado=f"/historia/{doc_target}",
        resultado="DENEGADO",
        detalle={"motivo": "El personal de admisión no tiene autorización para consultar historias clínicas completas"}
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Acceso denegado: El rol 'admisionista' no tiene permiso para consultar historias clínicas completas."
    )

