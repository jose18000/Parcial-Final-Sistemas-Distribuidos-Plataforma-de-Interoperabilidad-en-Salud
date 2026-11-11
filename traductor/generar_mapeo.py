"""
traductor/generar_mapeo.py
Genera docs/mapeo_57_campos.md a partir del catálogo (la documentación nunca se desfasa del código).

    python -m traductor.generar_mapeo
"""

import os

from traductor.catalogo_57 import CAMPOS_57, OBLIGATORIOS, SEDES
from traductor.dominios import DOMINIOS

RUTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "mapeo_57_campos.md")


PREFIJO_MONGO = {"usuario": "", "atencion": "atenciones[].", "tecnologia": "atenciones[].tecnologias[].",
                 "diagnostico": "atenciones[].", "egreso": "atenciones[]."}


def _ruta_mongo(c) -> str:
    # Los diagnósticos virtuales ya traen su ruta desde "diagnosticos[...]"
    return c.mongo


def generar() -> str:
    l = ["# Mapeo de los 57 campos de la historia clínica (traductor universal)", "",
         "> Generado automáticamente desde `traductor/catalogo_57.py` con `python -m traductor.generar_mapeo`.",
         "> No editar a mano.", "",
         "Referencia: Resolución 866 de 2021 (MinSalud) · `57_CAMPOS_HC.md` del repositorio de referencia.", "",
         "## Motores por sede", "", "| Sede | Ciudad | Motor | Código prestador (REPS sintético) |", "|---|---|---|---|"]
    for s, d in SEDES.items():
        l.append(f"| {s} | {d['ciudad']} | {d['motor']} | {d['codigo_prestador']} |")
    l += ["", f"**{len(CAMPOS_57)} campos**, {len(OBLIGATORIOS)} obligatorios (✅).", "",
          "Los campos que HL7 v2.5 no transporta viajan en segmentos Z de uso nacional: "
          "`ZPI` (datos complementarios del paciente), `ZPV` (atención), `ZRX` (finalidad del medicamento) "
          "y `ZEG` (egreso). Los diagnósticos 33-39 se guardan como filas de `diagnostico` con un rol "
          "(INGRESO, EGRESO, RELACIONADO) y el traductor los reconstruye.", ""]
    grupo = None
    for c in CAMPOS_57:
        if c.grupo != grupo:
            grupo = c.grupo
            l += ["", f"## {grupo}", "",
                  "| # | Campo | Oblig. | HL7 v2 | CSV | PostgreSQL (sedes 1 y 3) | MongoDB (sede 2) | FHIR R4 |",
                  "|---|---|---|---|---|---|---|---|"]
        der = " *(derivado)*" if c.derivado else ""
        l.append(f"| {c.num} | {c.nombre}{der} | {'✅' if c.obligatorio else ''} | `{c.hl7 or '—'}` | "
                 f"`{c.csv or '—'}` | `{c.pg}` | `pacientes.{PREFIJO_MONGO[c.contenedor]}{_ruta_mongo(c)}` | "
                 f"`{c.fhir}` |")
    l += ["", "## Dominios (valores permitidos y sinónimos que traduce)", ""]
    for nombre, dom in DOMINIOS.items():
        codigos = ", ".join(f"`{k}` {v}" for k, v in dom["codigos"].items())
        sinon = ", ".join(f"`{k}`→`{v}`" for k, v in dom["sinonimos"].items()) or "—"
        l += [f"- **{nombre}**: {codigos}. Sinónimos: {sinon}."]
    return "\n".join(l) + "\n"


if __name__ == "__main__":
    with open(RUTA, "w", encoding="utf-8") as f:
        f.write(generar())
    print(f"Escrito {RUTA}")
