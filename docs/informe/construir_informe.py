# -*- coding: utf-8 -*-
"""
Construye el informe final (plantilla v7 del docente) como documento Word.

    python docs/informe/construir_informe.py

- Copia la plantilla (no la modifica), conserva sus estilos y el orden de sus secciones, y
  reemplaza el texto de instrucciones y el contenido de ejemplo por el contenido del proyecto.
- Recorta las capturas muy altas en docs/informe/img/ (los originales no se tocan).
- Incluye las capturas 19-21 y las evidencias de docs/evidencias/ solo si existen:
  se puede volver a ejecutar cuando lleguen.
"""

import copy
import os
import re
import sys

from PIL import Image
import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph

# --------------------------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------------------------
AQUI = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.dirname(AQUI)
PLANTILLA = os.environ.get("PLANTILLA_V7", r"C:\Users\sharith\Desktop\Plantilla_Proyecto_Interoperabilidad_v7.docx")
SALIDA = os.path.join(AQUI, "Informe_Final_Plataforma_Interoperabilidad_v7.docx")
IMG = os.path.join(AQUI, "img")
CAPTURAS = os.path.join(DOCS, "capturas")
DIAGRAMAS = os.path.join(DOCS, "diagramas")
EVIDENCIAS = os.path.join(DOCS, "evidencias")

ANCHO_UTIL_CM = 15.5          # carta, márgenes de 3 cm de la plantilla
ALTO_MAX_CAPTURA_CM = 17.0
AZUL_CABECERA = "DBE5F1"
GRIS_CODIGO = "F2F2F2"


# --------------------------------------------------------------------------------------------
# Imágenes: recortes de las capturas altas
# --------------------------------------------------------------------------------------------
def _recortar(nombre, salida, franjas):
    """Guarda en img/ las franjas (y0, y1) de la captura, apiladas con un separador gris."""
    im = Image.open(os.path.join(CAPTURAS, nombre)).convert("RGB")
    w, h = im.size
    partes = [im.crop((0, max(0, a), w, min(h, b))) for a, b in franjas]
    sep = 6 if len(partes) > 1 else 0
    alto = sum(p.size[1] for p in partes) + sep * (len(partes) - 1)
    lienzo = Image.new("RGB", (w, alto), (190, 190, 190))
    y = 0
    for p in partes:
        lienzo.paste(p, (0, y))
        y += p.size[1] + sep
    ruta = os.path.join(IMG, salida)
    lienzo.save(ruta, optimize=True)
    return ruta


RECORTES = {   # captura -> lista de franjas en píxeles del original (1440 px de ancho)
    "08_admision_busqueda_1001.png": [(0, 1030)],
    "14_reporte_hc_1001.png": [(0, 1720)],
    "16_estado_plataforma.png": [(0, 1800)],
}
COMPUESTAS = {  # nombre de salida -> (captura, franjas)
    "14b_reporte_1001_cobertura_y_sello.png": ("14_reporte_hc_1001.png", [(3530, 3940), (4580, 4740)]),
    "15_reporte_1020_cobertura.png": ("15_reporte_57_campos_1020.png", [(0, 720), (2050, 2390)]),
    "19_reporte_incompleto_sede2_caida.png": ("19_reporte_incompleto_sede2_caida.png", [(0, 960), (1965, 2075)]),
}


def preparar_imagenes():
    os.makedirs(IMG, exist_ok=True)
    rutas = {}
    for f in sorted(os.listdir(CAPTURAS)):
        if not f.lower().endswith(".png"):
            continue
        origen = os.path.join(CAPTURAS, f)
        w, h = Image.open(origen).size
        if f in RECORTES:
            rutas[f] = _recortar(f, f, RECORTES[f])
        elif f.startswith("18_"):            # captura de móvil: se muestra completa y angosta
            rutas[f] = origen
        elif h > 1.35 * w:                   # cualquier otra captura de página completa
            rutas[f] = _recortar(f, f, [(0, int(1.25 * w))])
        else:
            rutas[f] = origen
    for salida, (f, franjas) in COMPUESTAS.items():
        if os.path.exists(os.path.join(CAPTURAS, f)):
            rutas[salida] = _recortar(f, salida, franjas)
    return rutas


# --------------------------------------------------------------------------------------------
# Utilidades de XML / python-docx
# --------------------------------------------------------------------------------------------
def _set_lang(rpr_parent):
    rpr = rpr_parent.get_or_add_rPr()
    lang = rpr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rpr.append(lang)
    lang.set(qn("w:val"), "es-CO")


def _shade(elem_pr, fill):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    elem_pr.append(shd)


def _campo(parrafo, instruccion, texto_previo=""):
    """Inserta un campo de Word (PAGE, TOC...) en el párrafo."""
    def fld(tipo):
        r = OxmlElement("w:r")
        c = OxmlElement("w:fldChar")
        c.set(qn("w:fldCharType"), tipo)
        r.append(c)
        return r
    p = parrafo._p
    p.append(fld("begin"))
    r = OxmlElement("w:r")
    t = OxmlElement("w:instrText")
    t.set(qn("xml:space"), "preserve")
    t.text = f" {instruccion} "
    r.append(t)
    p.append(r)
    p.append(fld("separate"))
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = texto_previo or "1"
    r.append(t)
    p.append(r)
    p.append(fld("end"))


TOKEN = re.compile(r"(\*\*.+?\*\*|`[^`]+`|(?<![\w*])\*[^*\s][^*]*?\*(?![\w*]))")


class Escritor:
    """Inserta contenido después de un elemento del cuerpo y avanza el cursor."""

    def __init__(self, doc):
        self.doc = doc
        self.cursor = None
        self.n_fig = 0
        self.n_tab = 0

    # -- básicos -----------------------------------------------------------------------------
    def _insertar(self, elem):
        self.cursor.addnext(elem)
        self.cursor = elem
        return elem

    def _nuevo_parrafo(self, estilo="Normal"):
        p = OxmlElement("w:p")
        self._insertar(p)
        par = Paragraph(p, self.doc._body)
        par.style = self.doc.styles[estilo]
        return par

    def _runs(self, par, texto, tam=None, cursiva=False, negrita=False, tam_codigo=None, color=None):
        for trozo in TOKEN.split(texto):
            if not trozo:
                continue
            b, i, code = negrita, cursiva, False
            if trozo.startswith("**") and trozo.endswith("**") and len(trozo) > 4:
                trozo, b = trozo[2:-2], True
            elif trozo.startswith("`") and trozo.endswith("`") and len(trozo) > 2:
                trozo, code = trozo[1:-1], True
            elif trozo.startswith("*") and trozo.endswith("*") and len(trozo) > 2:
                trozo, i = trozo[1:-1], True
            r = par.add_run(trozo)
            r.bold = b or None
            r.italic = i or None
            if code:
                r.font.name = "Consolas"
                r._element.rPr.rFonts.set(qn("w:hAnsi"), "Consolas")
                r.font.size = Pt(tam_codigo or ((tam - 1.5) if tam else 10))
            elif tam:
                r.font.size = Pt(tam)
            if color:
                r.font.color.rgb = RGBColor.from_string(color)
            _set_lang(r._element)
        return par

    # -- bloques -----------------------------------------------------------------------------
    def p(self, texto, alinear="justify", tam=None, cursiva=False, negrita=False, despues=6, antes=None,
          sangria_fr=None, estilo="Normal", mantener=False):
        par = self._nuevo_parrafo(estilo)
        self._runs(par, texto, tam=tam, cursiva=cursiva, negrita=negrita)
        f = par.paragraph_format
        f.alignment = {"justify": WD_ALIGN_PARAGRAPH.JUSTIFY, "center": WD_ALIGN_PARAGRAPH.CENTER,
                       "left": WD_ALIGN_PARAGRAPH.LEFT}[alinear]
        f.space_after = Pt(despues)
        if antes is not None:
            f.space_before = Pt(antes)
        if sangria_fr is not None:
            f.left_indent = Cm(sangria_fr)
            f.first_line_indent = Cm(-sangria_fr)
        if mantener:
            f.keep_with_next = True
        return par

    def sub(self, texto):
        """Título de párrafo en negrita (sin estilo de título, no entra en la tabla de contenido)."""
        return self.p(f"**{texto}**", alinear="left", despues=3, antes=6, mantener=True)

    def h(self, texto, nivel=2):
        par = self._nuevo_parrafo(f"Heading {nivel}")
        self._runs(par, texto)
        par.paragraph_format.space_after = Pt(6)
        return par

    def vinetas(self, items, tam=None):
        for it in items:
            par = self._nuevo_parrafo("List Bullet")
            self._runs(par, it, tam=tam)
            par.paragraph_format.space_after = Pt(3)
            par.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    def numerada(self, items):
        for k, it in enumerate(items, 1):
            par = self.p(f"{k}.\t{it}", sangria_fr=0.75, despues=4)
            par.paragraph_format.tab_stops.add_tab_stop(Cm(0.75))

    def salto_pagina(self):
        par = self._nuevo_parrafo()
        par.add_run().add_break(WD_BREAK.PAGE)

    def codigo(self, lineas, tam=8):
        """Bloque monoespaciado con fondo gris y borde (párrafos contiguos = una sola caja)."""
        for ln in lineas:
            par = self._nuevo_parrafo()
            r = par.add_run(ln if ln else " ")
            r.font.name = "Consolas"
            r._element.rPr.rFonts.set(qn("w:hAnsi"), "Consolas")
            r.font.size = Pt(tam)
            f = par.paragraph_format
            f.space_after = Pt(0)
            f.space_before = Pt(0)
            f.line_spacing = 1.0
            f.left_indent = Cm(0.2)
            f.right_indent = Cm(0.2)
            ppr = par._p.get_or_add_pPr()
            bdr = OxmlElement("w:pBdr")
            for lado in ("top", "left", "bottom", "right"):
                e = OxmlElement(f"w:{lado}")
                e.set(qn("w:val"), "single")
                e.set(qn("w:sz"), "4")
                e.set(qn("w:space"), "4")
                e.set(qn("w:color"), "A6A6A6")
                bdr.append(e)
            ppr.append(bdr)
            _shade(ppr, GRIS_CODIGO)
        self.p("", despues=4)

    def tabla(self, encabezados, filas, anchos=None, titulo=None, tam=9, centrar_cols=()):
        ncol = len(encabezados)
        t = self.doc.add_table(rows=1 + len(filas), cols=ncol)
        t.style = self.doc.styles["Table Grid"]
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        self._insertar(t._tbl)
        anchos = anchos or [1] * ncol
        total = float(sum(anchos))
        cms = [ANCHO_UTIL_CM * a / total for a in anchos]
        # anchos de la rejilla
        grid = t._tbl.tblGrid
        for gc, w in zip(grid.findall(qn("w:gridCol")), cms):
            gc.set(qn("w:w"), str(int(w * 567)))
        for i, fila in enumerate([encabezados] + filas):
            row = t.rows[i]
            if i == 0:
                trpr = row._tr.get_or_add_trPr()
                th = OxmlElement("w:tblHeader")
                trpr.append(th)
            for j, valor in enumerate(fila):
                cell = row.cells[j]
                cell.width = Cm(cms[j])
                par = cell.paragraphs[0]
                self._runs(par, str(valor), tam=tam, negrita=(i == 0), tam_codigo=tam - 1)
                f = par.paragraph_format
                f.space_after = Pt(1)
                f.space_before = Pt(1)
                f.line_spacing = 1.0
                if j in centrar_cols and i > 0:
                    f.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if i == 0:
                    _shade(cell._tc.get_or_add_tcPr(), AZUL_CABECERA)
        if titulo:
            self.n_tab += 1
            par = self.p(f"**Tabla {self.n_tab}.** {titulo}", alinear="center", tam=10, despues=10, antes=4)
        return t

    def figura(self, ruta, pie, ancho_cm=ANCHO_UTIL_CM, alto_max_cm=ALTO_MAX_CAPTURA_CM):
        w, h = Image.open(ruta).size
        ancho = min(ancho_cm, alto_max_cm * w / h)
        par = self._nuevo_parrafo()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.keep_with_next = True
        par.paragraph_format.space_before = Pt(6)
        par.paragraph_format.space_after = Pt(2)
        par.add_run().add_picture(ruta, width=Cm(ancho))
        self.n_fig += 1
        self.p(f"Figura {self.n_fig}. {pie}", alinear="center", tam=10, cursiva=True, despues=10)
        return self.n_fig

    def cambio_seccion(self, horizontal):
        """Termina la sección actual: la siguiente queda vertical u horizontal."""
        body_sect = self.doc.element.body.find(qn("w:sectPr"))
        nuevo = copy.deepcopy(body_sect)
        pgsz = nuevo.find(qn("w:pgSz"))
        pgmar = nuevo.find(qn("w:pgMar"))
        if horizontal:      # esta sección (la que termina) es la horizontal
            pgsz.set(qn("w:w"), "15840")
            pgsz.set(qn("w:h"), "12240")
            pgsz.set(qn("w:orient"), "landscape")
            for k, v in (("top", "1134"), ("bottom", "1134"), ("left", "1440"), ("right", "1440")):
                pgmar.set(qn(f"w:{k}"), v)
        par = self._nuevo_parrafo()
        par._p.get_or_add_pPr().append(nuevo)


# --------------------------------------------------------------------------------------------
# Figuras: orden y numeración
# --------------------------------------------------------------------------------------------
FIGS = {}   # clave -> número, se asigna al insertar


def ref(clave, con_parentesis=True):
    n = FIGS.get(clave)
    if not n:
        return ""
    return f" (Figura {n})" if con_parentesis else f"Figura {n}"


# --------------------------------------------------------------------------------------------
# Contenido
# --------------------------------------------------------------------------------------------
TITULO = "Plataforma distribuida de interoperabilidad clínica para una red de IPS con tres sedes heterogéneas"

RESUMEN = (
    "Una red de IPS con sedes en Sincelejo, Cartagena y Corozal guarda la historia clínica de cada "
    "paciente fraccionada en sistemas legados heterogéneos. El objetivo fue "
    "construir una plataforma distribuida que unifique esa historia sin reemplazar los sistemas legados. "
    "Se implementó un bus de servicios de salud (HSB) en FastAPI que recibe HL7 v2, CSV y JSON, los "
    "traduce con un catálogo de los 57 campos de la Resolución 866 de 2021 a un registro canónico, los "
    "valida y los entrega como Bundle FHIR R4 a HAPI FHIR y a la base de la sede: PostgreSQL en Sincelejo "
    "y Corozal, MongoDB en Cartagena. Una API con JWT, roles y un panel de administración consulta las tres "
    "sedes en paralelo y registra cada acceso en una cadena de auditoría SHA-256. En una máquina virtual "
    "Kali Linux, el sistema arrancó desde cero con un comando; el mensaje HL7 de prueba cubrió 56 de 57 campos y el 100 % de los "
    "obligatorios; la historia del paciente 1001 reunió 52 de 57 campos desde dos motores y su Bundle de "
    "26 recursos validó en HAPI sin errores. Reenviar un mensaje no creó duplicados; con HAPI apagado, el "
    "mensaje se entregó solo tras 7 intentos (unos 130 s); al detener la sede MongoDB, la consulta respondió "
    "con dos sedes y marcó el reporte incompleto; el verificador señaló el evento alterado. Pasaron 44 "
    "pruebas automatizadas. Un modelo canónico y entregas idempotentes permiten integrar motores "
    "heterogéneos sin transacciones distribuidas."
)

ABSTRACT = (
    "A network of healthcare providers with sites in Sincelejo, Cartagena and Corozal (Colombia) keeps each "
    "patient's clinical record split across legacy systems with different databases and message formats. "
    "The goal was to build a distributed platform that unifies that record without replacing the legacy "
    "systems. A health service bus (HSB) written in FastAPI receives HL7 v2, CSV and JSON, translates them "
    "through a single catalogue of the 57 fields of Colombian Resolution 866 of 2021 into a canonical "
    "record, validates them and delivers them as FHIR R4 transaction Bundles to HAPI FHIR and to each "
    "site's database (PostgreSQL in two sites, MongoDB in the third). An API with JWT, four clinical roles "
    "and an administration panel serves the role-based views, queries the three sites in parallel and logs "
    "every access in a SHA-256 hash chain. On a Kali Linux virtual machine with 3.8 GB of RAM, the full test "
    "HL7 message covered 56 of 57 fields; patient 1001 gathered 52 of 57 fields from two database engines and "
    "his 26-resource Bundle validated in HAPI with no errors. Resending a message created no duplicates; with "
    "HAPI down, the message was delivered automatically after 7 attempts (about 130 s); with the MongoDB site stopped, the "
    "query answered with two sites and flagged the report as incomplete; the verifier pointed to the altered "
    "audit event. All 44 automated tests passed."
)

PALABRAS_CLAVE = ("**Palabras clave:** sistemas distribuidos, interoperabilidad clínica, HL7 v2, FHIR R4, "
                  "Resolución 866 de 2021, MongoDB, teorema CAP, idempotencia.")
KEYWORDS = ("**Keywords:** distributed systems, clinical interoperability, HL7 v2, FHIR R4, Resolution 866 "
            "of 2021, MongoDB, CAP theorem, idempotency.")

REFERENCIAS = [
    "Bender, D., & Sartipi, K. (2013). HL7 FHIR: An agile and RESTful approach to healthcare information "
    "exchange. En *Proceedings of the 26th IEEE International Symposium on Computer-Based Medical Systems* "
    "(pp. 326–331). IEEE. https://doi.org/10.1109/CBMS.2013.6627810",
    "Centro Nacional en Sistemas de Información en Salud. (2022). *Guía de interoperabilidad clínica con HL7 "
    "FHIR en redes asistenciales*. CENS.",
    "HAPI FHIR Community. (2024). *HAPI FHIR: The open source FHIR API for Java* (versión 7.2.0). Smile "
    "Digital Health. https://hapifhir.io",
    "HL7 International. (2019). *FHIR Release 4 (v4.0.1)*. https://hl7.org/fhir/R4/",
    "Hohpe, G., & Woolf, B. (2003). *Enterprise integration patterns: Designing, building, and deploying "
    "messaging solutions*. Addison-Wesley.",
    "Ministerio de Salud de la Nación Argentina. (2020). *Estrategia nacional de salud digital: Guía de "
    "implementación del Perfil Argentino de FHIR*. Ministerio de Salud de la Nación.",
    "Ministerio de Salud y Protección Social. (2021). *Resolución 866 de 2021: Por la cual se reglamenta el "
    "conjunto de elementos de datos clínicos relevantes para la interoperabilidad de la historia clínica en "
    "el país*. MinSalud.",
    "NextGen Healthcare. (2023). *Mirth Connect integration engine technical reference guide*. NextGen "
    "Healthcare.",
    "OpenHIE Consortium. (2022). *Open Health Information Mediator (OpenHIM) architecture specification*. "
    "Jembi Health Systems.",
    "Tanenbaum, A. S., & Van Steen, M. (2017). *Distributed systems* (3.ª ed.). Maarten van Steen.",
]


def contar_palabras(texto):
    return len([w for w in re.split(r"\s+", texto) if re.search(r"\w", w)])


# ----- secciones ----------------------------------------------------------------------------
def s_resumen(w, img):
    w.p(RESUMEN)
    w.p(PALABRAS_CLAVE, alinear="left", despues=10)
    w.p("**Abstract**", alinear="left", despues=3, mantener=True)
    w.p(ABSTRACT, cursiva=False)
    w.p(KEYWORDS, alinear="left")


def s_introduccion(w, img):
    w.p("Cuando un paciente se atiende en Sincelejo, consulta por urgencias en Cartagena y hace sus controles "
        "en Corozal, cada sede guarda su parte de la historia clínica en su propio sistema. Ninguna sede ve la "
        "historia completa: se repiten exámenes, se pierde el registro de alergias o medicamentos y se toman "
        "decisiones con información parcial. Este es el problema de la **historia clínica fraccionada**.")
    w.p("El problema es relevante en Colombia porque la Resolución 866 de 2021 del Ministerio de Salud y "
        "Protección Social define el conjunto de 57 elementos de datos clínicos que deben poder "
        "intercambiarse entre prestadores (Ministerio de Salud y Protección Social, 2021). Cumplirla exige que "
        "sistemas construidos en épocas distintas, con bases y formatos distintos, hablen un mismo idioma "
        "sin que cada IPS tenga que reemplazar su sistema.")
    w.p("El reto del parcial es unificar la historia **sin reemplazar** los sistemas legados: cada sede "
        "conserva su base de datos, su motor y su formato de envío (HL7 v2 o CSV). En la versión 2 del "
        "proyecto se tomó esa heterogeneidad de forma literal, por indicación del docente: las sedes no usan "
        "el mismo motor. Sincelejo y Corozal usan PostgreSQL; Cartagena usa MongoDB, con un documento por "
        "paciente y nombres de campo distintos. La plataforma no puede suponer un esquema común.")
    w.p("La motivación técnica es aplicar en un sistema real los conceptos del curso de Sistemas Distribuidos: "
        "fallos parciales, el compromiso entre consistencia y disponibilidad (teorema CAP), transacciones "
        "ACID locales, fragmentación de datos por sede, mensajería con reintentos e idempotencia, y "
        "trazabilidad verificable. El resultado es un prototipo que se levanta con un solo comando, integra "
        "tres sedes con dos motores de base de datos, publica la información en FHIR R4 y ofrece vistas "
        "por rol (paciente, admisionista, médico, reporte de historia clínica) y un panel de administración.")
    w.p("El informe sigue la plantilla v7: primero el marco teórico, el marco conceptual y el estado del "
        "arte; luego la solución, el modelado UML, el proceso de desarrollo, las interfaces y el prototipo; "
        "después los resultados medidos, las conclusiones y los anexos, y al final las secciones de avance "
        "inicial, viabilidad técnica, interoperabilidad basada en datos y validación de los modelos UML.")


def s_objetivos(w, img):
    w.sub("Objetivo general")
    w.p("Diseñar, implementar y evaluar una plataforma distribuida que unifique la historia clínica de un "
        "paciente atendido en tres sedes con sistemas legados heterogéneos (HL7 v2 y CSV; PostgreSQL y "
        "MongoDB), usando FHIR R4 y los 57 campos de la Resolución 866 de 2021, sin reemplazar los sistemas "
        "legados.")
    w.sub("Objetivos específicos")
    w.numerada([
        "**Traducir** mensajes HL7 v2 (ADT^A01, ADT^A03, ORU^R01), filas CSV legadas y registros JSON de las "
        "tres sedes a un registro canónico de 57 campos, y medir la cobertura de campos por paciente (meta: "
        "100 % de los campos obligatorios en el mensaje de prueba completo).",
        "**Publicar** cada atención en HAPI FHIR R4 como Bundle `transaction` con `PUT` e identificadores "
        "deterministas, con 0 errores en la operación `$validate` y 0 recursos duplicados al reenviar un "
        "mensaje.",
        "**Reducir a una sola consulta** la búsqueda de la historia de un paciente con registros en tres sedes "
        "y dos motores, de modo que siga respondiendo si una sede cae y avise que el reporte está incompleto.",
        "**Controlar el acceso y la trazabilidad**: roles con permisos validados en la API (acceso denegado "
        "con código 403 y auditado), cuentas de usuario gestionadas por sede, auditoría encadenada por hash "
        "que señale el evento alterado exacto, y entrega automática de un mensaje cuando HAPI vuelve tras "
        "una caída.",
    ])


def s_marco_teorico(w, img):
    w.p("Esta sección resume los fundamentos que sustentan el diseño. Las definiciones operativas de los "
        "términos que se usan en el proyecto están en el marco conceptual.")
    w.sub("Sistemas distribuidos, transparencia y fallos parciales")
    w.p("Un sistema distribuido es un conjunto de computadores autónomos que el usuario percibe como un solo "
        "sistema coherente (Tanenbaum y Van Steen, 2017). La transparencia de ubicación oculta dónde están "
        "los datos; la transparencia de fallos busca que el sistema siga operando aunque falle una parte. "
        "Lo distintivo de un sistema distribuido es el **fallo parcial**: una sede puede caer mientras las "
        "otras siguen funcionando. En este proyecto el fallo no se oculta: la plataforma responde con lo que "
        "tiene y dice qué falta.")
    w.sub("Teorema CAP")
    w.p("Ante una partición de red, un sistema distribuido debe elegir entre consistencia (todas las réplicas "
        "ven el mismo dato) y disponibilidad (toda petición recibe respuesta). La consulta unificada de la "
        "plataforma es **AP**: si la sede 2 no responde, la historia se arma con las sedes 1 y 3 y se marca "
        "`reporte_completo = false`. Lo que se sacrifica es ver, en ese momento, las atenciones de la sede "
        "caída. La escritura es **eventualmente consistente**: el bus escribe primero en HAPI y luego en la "
        "sede; si la sede falla, el mensaje queda pendiente y se completa cuando la sede vuelve.")
    w.sub("Transacciones ACID")
    w.p("Atomicidad, consistencia, aislamiento y durabilidad describen una transacción local. En las sedes "
        "PostgreSQL, el usuario, la atención, los diagnósticos, las tecnologías en salud y el egreso se "
        "guardan en una sola transacción: o se guarda todo o no se guarda nada. En MongoDB la unidad atómica "
        "es el documento; como la atención completa está embebida en el documento del paciente, guardarla es "
        "una sola escritura atómica, sin transacciones multi-documento.")
    w.sub("Fragmentación horizontal y consulta distribuida")
    w.p("La fragmentación horizontal parte los datos por filas según un criterio. Aquí el criterio es la sede "
        "de la atención: cada sede guarda sus propias atenciones y la clave común entre sedes es el número "
        "de documento del paciente. Para reconstruir la historia, la API consulta las tres sedes al mismo "
        "tiempo y une los resultados en memoria (patrón *scatter-gather*; Hohpe y Woolf, 2003).")
    w.sub("Persistencia políglota")
    w.p("Usar motores de base de datos distintos según la necesidad de cada parte del sistema. Un modelo "
        "relacional normaliza la atención en varias tablas con llaves; un modelo documental guarda al "
        "paciente y sus atenciones en un solo documento. La plataforma no cambia los motores de las sedes: "
        "los trata a través de una interfaz común.")
    w.sub("HL7 versión 2")
    w.p("Estándar de mensajería clínica por segmentos de texto (`MSH`, `PID`, `PV1`, `DG1`, `OBX`, `RXE`…), "
        "con campos separados por `|` y componentes por `^`. El campo `MSH-10` identifica cada mensaje. Los "
        "datos que el estándar no trae se envían en **segmentos Z**, definidos por acuerdo entre las partes.")
    w.sub("HL7 FHIR R4")
    w.p("Estándar de HL7 basado en recursos (Patient, Encounter, Condition, Observation, MedicationRequest…) "
        "que se intercambian por una API REST en JSON (HL7 International, 2019). Un Bundle de tipo "
        "`transaction` agrupa recursos que el servidor procesa como una unidad. Frente a la sintaxis de HL7 "
        "v2, FHIR ofrece recursos con identidad propia y operaciones web estándar (Bender y Sartipi, 2013).")
    w.sub("Bus de integración e idempotencia")
    w.p("Un bus de integración desacopla a quien envía de quien recibe y concentra la traducción, la "
        "validación, el enrutamiento y los reintentos (Hohpe y Woolf, 2003). Cuatro patrones de esa obra "
        "guían el diseño: **modelo canónico de datos** (un formato pivote entre todos los formatos), "
        "**receptor idempotente** (un mensaje repetido no cambia el resultado), **canal de mensajes muertos** "
        "(los mensajes que no se pueden entregar se apartan para revisión) y **scatter-gather**. Una operación "
        "es idempotente si repetirla deja el mismo estado que hacerla una vez; es lo que permite reintentar "
        "sin miedo a duplicar.")
    w.sub("Integridad por encadenamiento de hash")
    w.p("Si cada registro de auditoría incluye el hash del registro anterior, modificar, borrar o reordenar "
        "un registro rompe la cadena desde ese punto. Recalcular la cadena permite señalar el primer registro "
        "alterado. Es el mismo principio de los registros encadenados, aplicado aquí sobre una tabla de "
        "PostgreSQL y no sobre una red de *blockchain*.")


def s_marco_conceptual(w, img):
    w.p("La tabla siguiente define los conceptos clave tal como se usan en el proyecto e indica dónde aparece "
        "cada uno. Después se explica cómo se relacionan.")
    w.tabla(["Concepto", "Definición en el proyecto", "Dónde aparece"], [
        ["FHIR R4", "Estándar de HL7 para intercambiar información clínica como recursos por REST.",
         "Servidor HAPI FHIR R4 v7.2.0 (`:8090/fhir`)"],
        ["Recurso", "Unidad de información FHIR con identidad propia: Patient, Encounter, Condition, Observation, "
         "MedicationRequest, AllergyIntolerance, Practitioner, Organization.", "`fhir/normalizer.py`"],
        ["Perfil y extensión", "Un perfil restringe un recurso para un uso concreto; una extensión agrega datos "
         "que el recurso base no trae. El proyecto usa extensiones propias, no un perfil publicado.",
         "URL base `https://minsalud.gov.co/fhir/StructureDefinition/`"],
        ["Bundle `transaction`", "Conjunto de recursos que HAPI procesa como una unidad; cada entrada usa `PUT` "
         "con un identificador determinista.", "`pac-<doc>`, `enc-<visita>`, `cond-…`, `obs-…`"],
        ["Terminología", "Sistema de códigos con significado compartido: CIE-10 para diagnósticos (`I10`, "
         "`J45.9`) y LOINC para laboratorio (`718-7`).", "Condition.code, Observation.code"],
        ["Dominio (Res. 866)", "Lista de valores permitidos de un campo (tipo de documento, entorno, triage, vía "
         "de ingreso…) con los sinónimos que usa cada sede.", "`traductor/dominios.py`"],
        ["API REST", "Interfaz por HTTP con recursos y verbos estándar (GET, POST, PUT).",
         "HSB (`:8001`), API Gateway (`:8000`), HAPI"],
        ["HSB", "Bus de servicios de salud: recibe, traduce, valida, normaliza, entrega y reintenta.",
         "`hsb/` (FastAPI)"],
        ["Catálogo de 57 campos", "Fuente única de verdad: para cada campo de la Res. 866 indica su origen HL7, "
         "CSV, su destino PostgreSQL, MongoDB y FHIR, si es obligatorio y su dominio.",
         "`traductor/catalogo_57.py`"],
        ["Registro canónico", "Representación intermedia y común de una atención con los 57 campos; pivote "
         "entre todos los formatos.", "`traductor/traductor.py`"],
        ["Traductor", "Módulo que convierte HL7, CSV o JSON al registro canónico, y el canónico a filas "
         "PostgreSQL, documento MongoDB o Bundle FHIR.", "`traductor/`"],
        ["Segmento Z", "Segmento HL7 v2 acordado entre las partes para datos sin lugar en el estándar.",
         "`ZPI`, `ZPV`, `ZRX`, `ZEG`"],
        ["Sede / nodo", "IPS con su propia base de datos (fragmento horizontal de la historia).",
         "`pg_sede1`, `mongo_sede2`, `pg_sede3`"],
        ["Consulta unificada", "Lectura en paralelo de las tres sedes que devuelve la historia y qué sedes "
         "respondieron.", "`db/consulta_unificada.py`"],
        ["Cobertura", "De campos: cuántos de los 57 tienen valor para un paciente. FHIR por sede: pacientes "
         "con recurso en HAPI sobre pacientes de la sede.", "Reporte de HC y tablero"],
        ["Evento de auditoría y sello", "Registro encadenado por SHA-256 de cada acceso o escritura; el hash "
         "del evento de una escritura es el sello que se devuelve al usuario.",
         "`pg_central.evento_auditoria`"],
        ["Rol y cuenta de usuario", "Paciente, admisionista, médico, auditor y administrador (general o de "
         "sede). Las cuentas se guardan en la base central con contraseña PBKDF2.",
         "`pg_central.usuario_sistema`"],
    ], anchos=[2.6, 7.4, 4.0], titulo="Conceptos clave del proyecto.")
    w.sub("Relación entre los conceptos")
    w.p("Un sistema de sede envía un mensaje HL7 v2 o una fila CSV al **HSB** por su **API REST**. El "
        "**traductor** lo lleva al **registro canónico** usando el **catálogo de 57 campos**; los **segmentos "
        "Z** aportan lo que HL7 no trae y los **dominios** unifican los códigos locales. El bus valida las "
        "**terminologías** (CIE-10, LOINC), arma un **Bundle transaction** con **recursos** FHIR y sus "
        "**extensiones**, lo publica en HAPI y guarda el mismo registro en la base de su **sede**. Para leer, "
        "la **consulta unificada** reúne las tres sedes, calcula la **cobertura** y deja un **evento de "
        "auditoría**. Cada acción depende del **rol** de la cuenta que inició sesión.")


def s_estado_arte(w, img):
    w.p("Se revisaron fuentes de alcance global, latinoamericano y colombiano sobre estándares y herramientas "
        "de interoperabilidad. La tabla resume qué aporta cada fuente al proyecto; las referencias completas "
        "están al final.")
    w.tabla(["#", "Fuente", "Alcance", "Qué se tomó para el proyecto"], [
        ["1", "Bender y Sartipi (2013)", "Global", "Argumentos a favor de FHIR (recursos REST) frente a la sintaxis "
         "de HL7 v2: base para publicar en FHIR y conservar HL7 v2 solo como formato de entrada de los legados."],
        ["2", "Centro Nacional en Sistemas de Información en Salud (2022)", "Latinoamérica (Chile)",
         "Uso de Observation con LOINC y Condition con CIE-10 en redes asistenciales."],
        ["3", "HAPI FHIR Community (2024)", "Global", "Servidor FHIR R4 de referencia, operación `$validate` y "
         "Bundles `transaction`."],
        ["4", "Hohpe y Woolf (2003)", "Global", "Patrones *Idempotent Receiver*, *Dead Letter Channel*, "
         "*Scatter-Gather* y *Canonical Data Model*, que el HSB implementa."],
        ["5", "Ministerio de Salud de la Nación Argentina (2020)", "Latinoamérica (Argentina)",
         "Experiencia nacional de implementación de FHIR con identificadores estables."],
        ["6", "Ministerio de Salud y Protección Social (2021)", "Colombia", "Resolución 866: los 57 datos de la "
         "historia clínica interoperable y sus dominios."],
        ["7", "NextGen Healthcare (2023)", "Global", "Mirth Connect como motor de integración HL7 de referencia."],
        ["8", "OpenHIE Consortium (2022)", "Global / países en desarrollo", "OpenHIM: separar la mediación "
         "(seguridad, auditoría) del almacenamiento."],
        ["9", "HL7 International (2019)", "Global", "Especificación FHIR R4: recursos, Bundle, transacciones y "
         "extensiones."],
        ["10", "Tanenbaum y Van Steen (2017)", "Global", "Fallos parciales, transparencia y consistencia en "
         "sistemas distribuidos."],
    ], anchos=[0.8, 3.6, 2.4, 7.2], titulo="Fuentes del estado del arte y aporte al proyecto.", centrar_cols=(0,))
    w.sub("Análisis crítico")
    w.p("Las experiencias nacionales revisadas (Chile y Argentina) coinciden en publicar la información clínica "
        "en FHIR con terminologías estándar e identificadores estables, y en dejar HL7 v2 para los sistemas "
        "existentes. Bender y Sartipi (2013) explican por qué: FHIR expone recursos con identidad propia por "
        "REST, mientras que HL7 v2 depende de acuerdos de sintaxis entre cada par de sistemas. Las "
        "herramientas de integración (Mirth Connect, OpenHIM, Apache Camel) resuelven el transporte y la "
        "mediación, pero suponen una plataforma de ejecución adicional y una configuración propia.")
    w.p("La brecha que aborda este proyecto es más pequeña y concreta: integrar sedes que no comparten ni el "
        "formato ni el motor de base de datos, y medir el cumplimiento de los 57 campos de la Resolución 866 "
        "de 2021 de punta a punta, desde el segmento HL7 hasta el elemento FHIR. En las fuentes revisadas no "
        "se encontró un perfil FHIR colombiano publicado que el proyecto pudiera usar; por eso los campos sin "
        "lugar en el recurso base se envían como extensiones propias.")
    w.sub("Comparación de herramientas")
    w.tabla(["Criterio", "HAPI FHIR", "Mirth Connect", "OpenHIM", "Apache Camel", "HSB propio (FastAPI)"], [
        ["Papel", "Servidor FHIR", "Motor de integración HL7", "Mediador de intercambio", "Marco de integración",
         "Bus del proyecto"],
        ["FHIR R4", "Nativo", "Por conectores", "Hacia un servidor FHIR externo", "Por componentes",
         "Cliente REST hacia HAPI"],
        ["HL7 v2", "Librería de lectura", "Nativo (canales)", "No es su foco", "Componente HL7",
         "Traductor propio guiado por catálogo"],
        ["Plataforma", "Java", "Java", "Node.js", "Java", "Python"],
        ["Configuración", "Código / propiedades", "Interfaz gráfica de canales", "Consola web", "DSL / código",
         "Código y catálogo de 57 campos"],
        ["Uso en el proyecto", "**Sí** (servidor FHIR)", "No", "No", "No", "**Sí** (bus)"],
    ], anchos=[2.2, 2.3, 2.4, 2.4, 2.3, 2.6], titulo="Comparación de HAPI FHIR, Mirth Connect, OpenHIM, Apache "
       "Camel y el HSB del proyecto.", tam=8.5)
    w.p("Se usa HAPI FHIR porque es la implementación abierta de referencia de FHIR R4, acepta Bundles "
        "`transaction`, ofrece `$validate` y el equipo ya la conocía del laboratorio. Para el bus se "
        "descartaron Mirth Connect, OpenHIM y Apache Camel porque cada integrante debe poder explicar y "
        "modificar en vivo cualquier parte del sistema (regla del parcial) y porque cada uno agrega otra "
        "plataforma de ejecución. A cambio, el proyecto renuncia a sus herramientas gráficas y a sus "
        "conectores ya construidos.")


def s_solucion(w, img):
    w.h("Arquitectura final")
    w.p("La plataforma son siete contenedores que se levantan con un solo comando "
        "(`docker compose down -v && docker compose up -d --build`). La Figura "
        f"{FIGS.get('arq', '1')} muestra los componentes y los flujos; la tabla resume el papel de cada "
        "contenedor.")
    FIGS["arq"] = w.figura(img["arquitectura"], "Arquitectura de la plataforma: tres sedes con su motor, HSB con "
                           "traductor de 57 campos, HAPI FHIR R4, API Gateway con las vistas por rol y base "
                           "central de auditoría y cuentas.", alto_max_cm=13)
    w.tabla(["Contenedor", "Papel", "Puerto"], [
        ["`pg_sede1`", "Sede 1 Sincelejo — PostgreSQL 16 (`clinica_sincelejo`)", "5433"],
        ["`mongo_sede2`", "Sede 2 Cartagena — MongoDB 7 (`clinica_cartagena`), un documento por paciente", "27018"],
        ["`pg_sede3`", "Sede 3 Corozal — PostgreSQL 16 (`clinica_corozal`)", "5435"],
        ["`pg_central`", "Base central: cadena de auditoría (`evento_auditoria`) y cuentas de usuario "
         "(`usuario_sistema`). No guarda datos clínicos.", "5436"],
        ["`hapi_fhir_r4`", "HAPI FHIR R4 v7.2.0", "8090"],
        ["`hsb_bus`", "Health Service Bus (FastAPI)", "8001"],
        ["`api_gateway`", "API Gateway, vistas por rol y panel de administración (FastAPI + Jinja2)", "8000"],
    ], anchos=[3, 10, 2], titulo="Contenedores de la plataforma.", centrar_cols=(2,))
    w.p("**Regla de oro.** Ninguna vista habla directo con las bases de las sedes. Las lecturas pasan por la "
        "consulta unificada de la API; las escrituras (admisión, diagnóstico, fórmula, egreso) viajan al HSB "
        "por `/hsb/json` y siguen el mismo camino que un mensaje HL7. El diagrama editable está en Mermaid en "
        "`docs/fase1/arquitectura/arquitectura_y_justificacion.md`, junto con la tabla que justifica cada "
        "componente frente al requisito que cubre.")

    w.h("Tecnologías empleadas")
    w.vinetas([
        "**Lenguaje y servicios:** Python 3.11, FastAPI y Uvicorn para el HSB y la API; Jinja2 para las vistas.",
        "**Datos:** PostgreSQL 16 (sedes 1 y 3, base central), MongoDB 7 (sede 2), con psycopg2 y PyMongo.",
        "**Estándares:** HL7 v2.5 (ADT^A01, ADT^A03, ORU^R01, RDE^O11), FHIR R4 en HAPI FHIR 7.2.0, CIE-10 y "
        "LOINC.",
        "**Seguridad:** JWT HS256, contraseñas PBKDF2-SHA256 (200 000 iteraciones, sal por usuario), SHA-256 "
        "para la cadena de auditoría.",
        "**Despliegue y pruebas:** Docker Compose; manifiestos de Kubernetes para Minikube en `infra/k8s/`; "
        "`pytest`. Diagramas en Mermaid.",
    ])

    w.h("Capa de datos")
    w.vinetas([
        "**Un nodo por sede (RF4).** Cada IPS conserva su base; no hay base central de datos clínicos.",
        "**Motores distintos.** Las sedes 1 y 3 usan el esquema relacional de 57 campos (`db/schema.sql`): "
        "`usuario`, `atencion`, `diagnostico`, `tecnologia_salud`, `egreso`, `profesional_salud`, `sede` y "
        "`mensaje_bus`. La sede 2 usa la colección `pacientes`, con un documento por paciente y sus atenciones "
        "embebidas, más `mensajes_bus`, `profesionales` y `sedes`. Los nombres no coinciden a propósito "
        "(`identificacion.numero` frente a `documento_id`).",
        "**Repositorio con una sola interfaz.** `RepositorioPostgres` y `RepositorioMongo` (`db/repositorio.py`) "
        "exponen los mismos métodos (`guardar`, `historia`, `cobertura_fhir` y los de `mensaje_bus`) y hablan "
        "siempre en el registro canónico. El bus y la API no saben qué motor tiene cada sede.",
        "**ACID local.** En PostgreSQL, `guardar` hace UPSERT de las cinco tablas en una transacción; en "
        "MongoDB reemplaza el documento completo del paciente con `replace_one`, que es atómico.",
        "**Sin transacción distribuida.** No hay 2PC entre sedes ni entre HAPI y la sede: la entrega es "
        "idempotente y se reintenta hasta completarse.",
    ])

    w.h("Traductor universal de 57 campos")
    w.vinetas([
        "`catalogo_57.py` es la fuente única de verdad: para cada campo indica el segmento HL7, la columna CSV, "
        "la `tabla.columna` de PostgreSQL, la ruta del documento MongoDB y el elemento FHIR, si es obligatorio "
        "(23 lo son) y su dominio.",
        "`dominios.py` guarda los códigos permitidos y los sinónimos de cada sede (por ejemplo, `E` en PV1-2 "
        "equivale al entorno `01` Urgencias, el triage `III` a `3` y la vía `PO` a `01` Oral).",
        "`traductor.py` convierte HL7, CSV o JSON al registro canónico y este a filas PostgreSQL, documento "
        "MongoDB o Bundle FHIR. Con tres entradas y tres salidas se escriben seis traducciones y no nueve.",
        "Los campos que HL7 v2.5 no trae viajan en segmentos Z: `ZPI` (datos complementarios del paciente), "
        "`ZPV` (modalidad y triage), `ZRX` (finalidad del medicamento) y `ZEG` (egreso).",
        "Edad, unidad de edad y código del prestador se derivan; la cobertura de campos se calcula por paciente "
        "con la lista de faltantes. El mapeo completo se genera en `docs/mapeo_57_campos.md`.",
    ])

    w.h("Bus de servicios de salud (HSB)")
    w.p("Entradas `POST /hsb/hl7`, `POST /hsb/csv?sede=N` y `POST /hsb/json?sede=N`; operación "
        "`GET /hsb/mensajes`, `GET /hsb/catalogo`, `POST /hsb/reencolar/{id}`, `GET /health` y `GET /metrics`. "
        "El flujo de cada mensaje (`hsb/ingesta.py`, `hsb/queue_manager.py`) es:")
    w.numerada([
        "**Traducir** al registro canónico.",
        "**Verificar idempotencia:** busca `MSH-10` (o el hash SHA-256 de la fila CSV o del JSON) en "
        "`mensaje_bus` de la sede; si ya está ENTREGADO, TRANSFORMADO o REINTENTANDO responde `duplicado`.",
        "**Validar** documento, nombre, sexo, sede, fechas, CIE-10 y LOINC; si algo falla, RECHAZADO con "
        "todos los motivos.",
        "**Normalizar** a un Bundle `transaction` con `PUT` e identificadores deterministas.",
        "**Entregar** primero a HAPI y después a la sede; ambos pasos son idempotentes.",
        "**Reintentar** en segundo plano con esperas de 2, 4, 8, 16, 32 y 64 s (`HSB_MAX_RETRIES=7`); al "
        "agotarlos, MUERTO, con opción de reencolar. Los errores de datos (restricción violada, HTTP 4xx de "
        "HAPI) van directo a MUERTO. Al reiniciar, el bus recupera los mensajes pendientes de las sedes.",
    ])

    w.h("Seguridad, cuentas de usuario y panel de administración")
    w.vinetas([
        "**JWT HS256** de 60 minutos emitido en `/auth/login`; viaja en cookie para las vistas o como `Bearer`.",
        "**Roles validados en la API:** paciente (solo su historia), admisionista (búsqueda y admisión, sin "
        "diagnósticos), médico (historia unificada y escrituras clínicas), auditor (reporte, tablero y "
        "verificador; en el panel solo consulta) y administrador. Un acceso no permitido responde 403 y "
        "deja un evento `ACCESO_DENEGADO`.",
        "**Cuentas en la base central** (`usuario_sistema`) con contraseña PBKDF2-SHA256 y trazabilidad del "
        "registro: origen (`SEMILLA`, `PANEL` o `ADMISION`), quién la creó, cuándo y último acceso. El "
        "administrador general gestiona cuentas de toda la red; el administrador de sede solo crea y "
        "gestiona médicos, admisionistas y pacientes de su sede.",
        "**Cuenta del portal del paciente:** al admitir a un paciente nuevo se crea su cuenta (usuario = número "
        "de documento) con una contraseña temporal que se muestra una sola vez; en el primer ingreso el sistema "
        "obliga a cambiarla antes de permitir cualquier otra pantalla.",
        "**Auditoría encadenada** en `pg_central.evento_auditoria`: `hash_propio = SHA-256(hash_anterior | "
        "índice | fecha | usuario | rol | tipo | recurso | resultado | detalle)`, con `pg_advisory_xact_lock` "
        "para que dos inserciones simultáneas no enlacen al mismo hash anterior.",
        "**Panel de administración** (`/panel`): una pantalla que se actualiza cada 5 s con las secciones "
        "Resumen, Pacientes, Usuarios, Integración, FHIR y Auditoría.",
        "**Datos sintéticos:** `scripts/generar_datos_prueba.py` genera pacientes ficticios en las tres sedes y "
        "los envía por el bus (HL7 v2 con segmentos Z y CSV), incluidos errores y reenvíos a propósito; es "
        "determinista y no crea copias si se repite.",
    ])

    w.h("Metodología y hoja de ruta")
    w.p("Se trabajó de forma iterativa en cinco fases, cada una con un entregable funcional y revisión cruzada "
        "entre los dos integrantes. Cada fase partió del código de la anterior; las correcciones entre fases "
        "se anotaron en la bitácora (`docs/bitacora.md`). Después de la Fase 5 se hizo una mejora (v2) que "
        "reescribió la capa de datos, el bus y la auditoría.")
    w.tabla(["Fase", "Entregable", "Estado"], [
        ["1. Análisis, UML y diseño", "Informe, 4 diagramas, arquitectura, mapeo de campos",
         "Entregada; diagramas actualizados a v2"],
        ["2. Datos distribuidos y FHIR", "Nodos por sede, normalizador FHIR, demostración ACID",
         "Entregada; en v2, esquema de 57 campos y sede 2 en MongoDB"],
        ["3. HSB", "Bus HL7/CSV con reintentos e idempotencia",
         "Entregada; en v2, cola en segundo plano, recuperación y `/hsb/json`"],
        ["4. Seguridad y resiliencia", "JWT, roles, auditoría, caída de sede",
         "Entregada; en v2, auditoría persistida en `pg_central`"],
        ["5. Prototipo final", "Vistas, informe, sustentación", "Este informe"],
        ["Mejora v2 (10 y 11 de nov.)", "Traductor de 57 campos, MongoDB, panel de administración, gestión de "
         "usuarios, generador de datos", "Implementada y probada (44 pruebas)"],
    ], anchos=[3.6, 6.2, 5.2], titulo="Hoja de ruta de las fases del proyecto.")


def s_uml_intro(w, img):
    pass


def s_uml_casos(w, img):
    w.p("El modelado se hizo con cuatro diagramas UML escritos en **Mermaid**. El código fuente editable está "
        "en `docs/fase1/diagramas/` (archivos `01_casos_uso.md`, `02_secuencia_hsb.md`, `03_clases.md` y "
        "`04_estados_mensaje.md`) y las imágenes renderizadas en `docs/diagramas/`. Cada archivo fuente "
        "incluye una tabla de coherencia con los otros tres diagramas.")
    w.p("El diagrama de casos de uso" + ref("uc") + " tiene cinco actores (paciente, admisionista, médico, "
        "auditor y sistema de sede) y 17 casos de uso. Los casos UC1 a UC13 corresponden a las vistas por rol; "
        "UC14 y UC15 al envío y procesamiento de mensajes por el bus; UC16 y UC17 los ejecuta la API "
        "(registrar un evento de auditoría y rechazar con 403 una acción no permitida). La separación entre "
        "admisión (UC5) y registro clínico (UC8) aplica el mínimo privilegio: la admisionista no ve "
        "diagnósticos.")
    FIGS["uc"] = w.figura(img["uml_01_casos_uso"], "Diagrama de casos de uso: actores, límite del sistema y "
                          "relaciones «include» y «extend». Fuente: `docs/fase1/diagramas/01_casos_uso.md`.",
                          alto_max_cm=19)


def s_uml_secuencia(w, img):
    w.p("El diagrama de secuencia" + ref("seq") + " sigue un mensaje HL7 v2 desde el sistema de la sede hasta "
        "HAPI FHIR y la base de la sede, con los caminos alternativos de duplicado, rechazo, error de datos "
        "(directo a MUERTO) y reintento en segundo plano. Termina con la consulta del médico, que reúne las "
        "tres sedes en paralelo y deja su evento en la cadena de auditoría. El orden HAPI primero y sede "
        "después es seguro porque los dos pasos son idempotentes. Por su tamaño se presenta en una página "
        "horizontal.")
    w.cambio_seccion(horizontal=False)
    FIGS["seq"] = w.figura(img["uml_02_secuencia"], "Diagrama de secuencia del procesamiento de un mensaje HL7 "
                           "v2 en el HSB y de la consulta unificada. Fuente: `docs/fase1/diagramas/"
                           "02_secuencia_hsb.md`.", ancho_cm=22.8, alto_max_cm=15.6)
    w.cambio_seccion(horizontal=True)


def s_uml_clases(w, img):
    w.p("El diagrama de clases" + ref("cls") + " tiene tres grupos: el dominio clínico de la Resolución 866 "
        "(`Usuario`, `Atencion`, `Diagnostico`, `TecnologiaSalud`, `Egreso`, `ProfesionalSalud`, `Sede`), el "
        "traductor (`Campo`, `RegistroCanonico`) y la infraestructura (`MensajeBus`, `EventoAuditoria`, "
        "`UsuarioSistema` y la jerarquía `RepositorioSede` ← `RepositorioPostgres` / `RepositorioMongo`). "
        "`Usuario` es el paciente, como lo llama la resolución; quien inicia sesión es `UsuarioSistema`. Los "
        "diagnósticos 33 a 39 se modelan como filas con un rol (INGRESO, EGRESO, RELACIONADO).")
    FIGS["cls"] = w.figura(img["uml_03_clases"], "Diagrama de clases del dominio, del traductor y de la "
                           "infraestructura. Fuente: `docs/fase1/diagramas/03_clases.md`.", alto_max_cm=15.5)


def s_uml_estados(w, img):
    w.p("El diagrama de estados" + ref("est") + " describe el ciclo de vida de un `MensajeBus` con los siete "
        "estados que pide la guía: RECIBIDO, VALIDADO, TRANSFORMADO, ENTREGADO, RECHAZADO, REINTENTANDO y "
        "MUERTO. El estado se guarda en `mensaje_bus` de la sede del mensaje, por eso sobrevive a un reinicio "
        "del bus. \"Duplicado\" no es un estado: es la respuesta del bus cuando el mensaje ya existe.")
    FIGS["est"] = w.figura(img["uml_04_estados"], "Diagrama de estados del mensaje en el bus. Fuente: "
                           "`docs/fase1/diagramas/04_estados_mensaje.md`.", alto_max_cm=12)
    w.tabla(["Desde", "Hacia", "Disparador"], [
        ["RECIBIDO", "(respuesta `duplicado`)", "El identificador o el hash ya existe en ENTREGADO, TRANSFORMADO "
         "o REINTENTANDO"],
        ["RECIBIDO", "RECHAZADO", "Falla al menos una regla de validación; se guardan todos los motivos"],
        ["RECIBIDO", "VALIDADO", "Todas las reglas pasan"],
        ["VALIDADO", "TRANSFORMADO", "Bundle FHIR construido"],
        ["TRANSFORMADO", "ENTREGADO", "HAPI responde 200/201 y la sede guarda"],
        ["TRANSFORMADO", "REINTENTANDO", "HAPI o la sede no responden (caída o tiempo de espera agotado)"],
        ["TRANSFORMADO / REINTENTANDO", "MUERTO", "Error de datos: HAPI 4xx o restricción violada en la sede"],
        ["REINTENTANDO", "ENTREGADO / MUERTO", "Un reintento tiene éxito / se completan 7 intentos"],
        ["MUERTO", "REINTENTANDO", "Un operador llama `POST /hsb/reencolar/{id}`"],
    ], anchos=[3.6, 3.4, 8], titulo="Transiciones del diagrama de estados.")
    w.sub("Reglas de validación antes de transformar")
    w.p("El validador (`hsb/validator.py`) aplica estas reglas antes de construir el Bundle. Un valor opcional "
        "fuera de su dominio no rechaza el mensaje: el traductor lo omite y el bus devuelve una advertencia.")
    w.tabla(["Campo", "Regla", "Motivo de rechazo"], [
        ["Documento (campo 2)", "No vacío, solo dígitos, de 4 a 15", "`documento no numérico` / `documento fuera "
         "de rango`"],
        ["Nombre (4)", "No vacío", "`nombre no puede ser vacío`"],
        ["Sexo (8)", "`M`, `F` u `O` (después de aplicar sinónimos)", "`sexo no válido`"],
        ["Sede", "1, 2 o 3 (`MSH-4` o `?sede=N`)", "`sede no válida o desconocida`"],
        ["Fecha de nacimiento (5)", "Válida y no futura", "`fecha de nacimiento no válida` / `en el futuro`"],
        ["Fecha de ingreso (17)", "Válida si viene", "`fecha de ingreso no válida`"],
        ["Diagnósticos (34, 36–39)", "CIE-10 `^[A-Z][0-9]{2}(\\.[0-9]{1,4})?$`; en HL7 no se acepta el "
         "sistema local `L`; en CSV el texto local se mapea con `05_ref_terminologia.csv`",
         "`diagnóstico sin mapeo a CIE-10`"],
        ["Laboratorio", "LOINC `^[0-9]+-[0-9]+$`", "`código LOINC inválido`"],
        ["Medicamento (25)", "Descripción presente", "`medicamento sin descripción`"],
    ], anchos=[3.4, 6.6, 5], titulo="Reglas de validación del mensaje antes de transformarlo.")


def s_proceso(w, img):
    w.p("El desarrollo siguió las etapas de análisis, diseño, desarrollo, pruebas y despliegue en cada una de "
        "las cinco fases del parcial, más una mejora final (v2).")
    w.vinetas([
        "**Análisis y diseño (Fase 1):** problema, actores y casos de uso, los cuatro diagramas UML, "
        "arquitectura con justificación de componentes y tabla de mapeo de campos.",
        "**Desarrollo por fases:** cada fase partió del código de la anterior (datos y FHIR, bus, seguridad, "
        "vistas). En la v2 se reescribieron la capa de datos (57 campos y MongoDB), el bus (cola persistente "
        "con trabajador en segundo plano) y la auditoría (persistida), y se agregaron el traductor, el panel "
        "de administración, la gestión de cuentas y el generador de datos sintéticos.",
        "**Correcciones entre fases:** se registraron en la bitácora. Por ejemplo, la auditoría vivía solo en "
        "memoria (se pasó a `pg_central`), los reintentos bloqueaban la petición y terminaban en MUERTO antes "
        "de que HAPI volviera (cola en segundo plano con esperas hasta 64 s) y reentregar un mensaje "
        "duplicaba diagnósticos (identificadores deterministas y UPSERT).",
        "**Despliegue:** Docker Compose con un solo comando; las imágenes del HSB y de la API se construyen "
        "desde el repositorio. Los puertos se pueden reasignar en `.env`. Se incluyen manifiestos de "
        "Kubernetes para Minikube en `infra/k8s/`; este informe no presenta evidencia de su ejecución.",
        "**CI/CD:** no se configuró un pipeline de integración continua. Las pruebas se corren localmente "
        "antes de cada cambio (`python -m pytest tests/ -v`). Queda como trabajo futuro.",
        "**Control de versiones:** repositorio Git con 16 commits de ambos integrantes en las cinco fases y "
        "la etiqueta `v1.0`. Los cambios de la mejora v2 se documentan en la bitácora.",
        "**Uso declarado de IA:** Antigravity (Google DeepMind) en las fases 1 a 5 y Claude Code (Anthropic) "
        "en la mejora v2, con revisión y pruebas de los integrantes (Anexo F).",
    ])
    w.sub("Pruebas automatizadas")
    w.p("Se escribieron 44 pruebas con `pytest`, organizadas por fase. Todas pasan (`44 passed`, ejecución "
        "local del 11 de noviembre de 2026). Además se hicieron las pruebas en vivo sobre Docker que se "
        "reportan en Resultados.")
    w.tabla(["Suite", "Pruebas", "Qué cubre"], [
        ["`tests/fase2/test_normalizer.py`", "8", "Recursos FHIR, identificadores deterministas, referencias "
         "internas, caso inválido"],
        ["`tests/fase2/test_traductor_57.py`", "10", "Catálogo de 57 campos, columnas de `db/schema.sql` frente "
         "al catálogo, ida y vuelta MongoDB, CSV, JSON por número de campo"],
        ["`tests/fase3/test_hsb_integration.py`", "11", "Los 4 ejemplos oficiales, idempotencia HL7 y CSV, "
         "reintento, muerto y reencolar, error de datos, sede caída"],
        ["`tests/fase4/test_security_resilience.py`", "8", "Permisos por rol (403 y auditoría), cadena de hash "
         "y alteración, resiliencia"],
        ["`tests/fase4/test_usuarios.py`", "7", "Cuentas semilla, administrador de sede limitado a su sede, "
         "auditor de solo lectura, contraseña temporal y cambio obligatorio, cuenta del paciente al admitir"],
        ["**Total**", "**44**", ""],
    ], anchos=[5.4, 1.6, 8], titulo="Pruebas automatizadas por suite.", centrar_cols=(1,))


def s_interfaces(w, img):
    w.p("Las vistas son plantillas Jinja2 servidas por la API en `http://localhost:8000`. Comparten un marco "
        "común (barra superior con la red de IPS, el usuario y su rol) y solo muestran las opciones que el "
        "rol puede usar; aun así, los permisos se validan en la API y no en la pantalla. Las capturas se "
        "tomaron el 11 de noviembre de 2026 sobre la plataforma desplegada con Docker, con datos sintéticos, "
        "a 1440 px de ancho; las capturas de página completa se recortaron a la parte relevante (originales "
        "en `docs/capturas/`).")
    w.tabla(["Vista", "Ruta", "Usuario de prueba", "Qué muestra"], [
        ["Inicio de sesión", "`/login`", "todos", "Formulario y accesos de demostración por rol"],
        ["Panel de administración", "`/panel`", "`admin_plataforma`, administradores de sede, auditor (lectura)",
         "Resumen en vivo, pacientes, usuarios, integración, FHIR y auditoría"],
        ["Admisionista", "`/admision`", "`admision_laura`", "Búsqueda en las 3 sedes, posible duplicado, "
         "admisión con triage, cuenta del portal, envíos al bus. Sin diagnósticos"],
        ["Paciente", "`/paciente`", "`paciente_carlos` o la cuenta creada al admitir", "Su historia de las 3 "
         "sedes, descarga del Bundle FHIR y accesos a su historia"],
        ["Médico", "`/medico`", "`medico_mateo`", "Historia unificada; diagnóstico CIE-10, fórmula y egreso con "
         "código de verificación"],
        ["Reporte de HC y estado", "`/reporte`", "médico, auditor, paciente (solo el suyo)", "Reporte por sede, "
         "57 campos con faltantes, sello, impresión, Bundle; pestaña de estado de la plataforma"],
    ], anchos=[2.8, 1.9, 3.8, 6.5], titulo="Vistas de la plataforma.")

    w.h("Inicio de sesión y diseño adaptable")
    w.p("La pantalla de inicio" + ref("login") + " muestra el formulario y, por ser un prototipo con datos "
        "sintéticos, los usuarios de demostración. La misma pantalla a 390 px de ancho con el tema oscuro del "
        "sistema operativo" + ref("movil") + " comprueba el diseño adaptable.")
    if "01_login.png" in img:
        FIGS["login"] = w.figura(img["01_login.png"], "Inicio de sesión con los usuarios de demostración por rol.")
    if "18_login_movil_oscuro.png" in img:
        FIGS["movil"] = w.figura(img["18_login_movil_oscuro.png"], "Inicio de sesión a 390 px de ancho con el "
                                 "tema oscuro del sistema.", alto_max_cm=11)

    w.h("Panel de administración")
    w.p("El panel se actualiza solo cada 5 segundos y tiene seis secciones. El **Resumen**" + ref("p_res") +
        " reúne indicadores (sedes activas, servidor FHIR, cobertura FHIR, mensajes, latencia media, "
        "porcentaje de fallidos, eventos de auditoría), el estado de cada sede con su motor y los últimos "
        "mensajes y eventos. **Pacientes**" + ref("p_pac") + " lista los pacientes de las tres sedes con su "
        "sede y si ya están en FHIR, y permite registrar uno nuevo. **Usuarios**" + ref("p_usr") + " muestra "
        "las cuentas con su rol, sede, estado, origen del registro y último acceso, con acciones para "
        "desactivar o restablecer la contraseña. **Integración**" + ref("p_int") + " muestra los mensajes por "
        "estado y las métricas del bus; **FHIR**" + ref("p_fhir") + " los recursos en HAPI por tipo, y "
        "**Auditoría**" + ref("p_aud") + " el estado de la cadena y los últimos eventos con su hash.")
    for clave, f, pie in [
        ("p_res", "02_panel_resumen.png", "Panel de administración, sección Resumen: indicadores, sedes con su "
         "motor, mensajes y eventos recientes."),
        ("p_pac", "03_panel_pacientes.png", "Panel, sección Pacientes: pacientes de las tres sedes con su sede "
         "y su estado en FHIR."),
        ("p_usr", "04_panel_usuarios.png", "Panel, sección Usuarios: cuentas con rol, sede, estado y origen del "
         "registro (carga inicial, panel o admisión)."),
        ("p_int", "05_panel_integracion.png", "Panel, sección Integración: mensajes del bus por estado y "
         "métricas (latencia media, fallidos, duplicados, reintentos)."),
        ("p_fhir", "06_panel_fhir.png", "Panel, sección FHIR: cobertura y recursos en HAPI FHIR por tipo."),
        ("p_aud", "07_panel_auditoria.png", "Panel, sección Auditoría: cadena ÍNTEGRA, último hash y últimos "
         "eventos."),
    ]:
        if f in img:
            FIGS[clave] = w.figura(img[f], pie)

    w.h("Admisión y cuenta del paciente")
    w.p("La admisionista busca por documento" + ref("adm1") + ": la vista indica en qué sedes existe el "
        "paciente (con el motor de cada una), advierte un posible duplicado entre sedes y lista las atenciones "
        "anteriores sin contenido clínico. Al admitir a un paciente nuevo" + ref("adm2") + ", el HSB entrega "
        "la atención, la vista muestra los recursos FHIR creados y el código de verificación, y aparece la "
        "cuenta del portal del paciente con su contraseña temporal, que se muestra una sola vez. En el primer "
        "ingreso del paciente el sistema obliga a cambiarla" + ref("clave") + ".")
    for clave, f, pie in [
        ("adm1", "08_admision_busqueda_1001.png", "Admisión: el documento 1001 está registrado en las 3 sedes "
         "(PostgreSQL, MongoDB, PostgreSQL), aviso de posible duplicado y atenciones sin diagnósticos."),
        ("adm2", "09_admision_paciente_y_cuenta.png", "Admisión de un paciente nuevo en la Sede 2: respuesta "
         "del bus, recursos FHIR, cuenta del portal con contraseña temporal y código de verificación."),
        ("clave", "10_cambio_clave_obligatorio.png", "Cambio de contraseña obligatorio en el primer ingreso del "
         "paciente."),
    ]:
        if f in img:
            FIGS[clave] = w.figura(img[f], pie)

    w.h("Portal del paciente")
    w.p("El paciente ve sus datos, su historia ordenada por fecha con la sede de cada atención, un botón para "
        "descargar su Bundle FHIR y la lista de accesos a su historia: quién, con qué rol, qué hizo, el "
        "resultado y el código de verificación de cada evento" + ref("portal") + ". Esta lista responde al "
        "derecho de acceso de la Ley 1581 de 2012.")
    if "11_portal_paciente.png" in img:
        FIGS["portal"] = w.figura(img["11_portal_paciente.png"], "Portal del paciente: datos, historia clínica "
                                  "y accesos a su historia con su código de verificación.")

    w.h("Consulta médica")
    w.p("El médico busca la historia unificada" + ref("med1") + " y registra diagnóstico CIE-10, fórmula "
        "(campos 25 a 32) o egreso (campos 40 a 50). Cada escritura viaja por el HSB y devuelve un código de "
        "verificación, que es el hash del evento de auditoría de esa escritura" + ref("med2") + ". El "
        "profesional se toma del token, no del formulario: el médico no puede registrar a nombre de otro.")
    for clave, f, pie in [
        ("med1", "12_medico_historia_1020.png", "Consulta médica del paciente 1020: historia con la sede y el "
         "motor, y formularios de registro clínico."),
        ("med2", "13_medico_registro_con_codigo.png", "Registro clínico guardado: el médico recibe el código de "
         "verificación (sello SHA-256) de la escritura."),
    ]:
        if f in img:
            FIGS[clave] = w.figura(img[f], pie)

    w.h("Reporte de historia clínica y estado de la plataforma")
    w.p("El Reporte de HC agrupa la historia por sede, indica si el reporte está completo, ofrece imprimir y "
        "descargar el Bundle FHIR" + ref("rep") + ", y al final muestra la completitud de los 57 campos, la "
        "lista de faltantes y el código de verificación del reporte (SHA-256 del contenido). La pestaña "
        "Estado de la plataforma" + ref("estado") + " reúne las sedes con su motor y latencia, la cobertura "
        "FHIR por sede, las métricas del bus y la cadena de auditoría con su prueba de integridad.")
    if "14_reporte_hc_1001.png" in img:
        FIGS["rep"] = w.figura(img["14_reporte_hc_1001.png"], "Reporte de HC del paciente 1001 (parte superior): "
                               "reporte completo de 3 sedes, agrupado por sede.")
    if "16_estado_plataforma.png" in img:
        FIGS["estado"] = w.figura(img["16_estado_plataforma.png"], "Estado de la plataforma: sedes y su motor, "
                                  "bus de integración y cadena de auditoría.")

    w.h("Experiencia de usuario y accesibilidad")
    w.vinetas([
        "**Contraste:** texto oscuro sobre fondo claro y estados con colores de contraste suficiente (criterio "
        "AA de WCAG como referencia); el tema oscuro respeta la preferencia del sistema.",
        "**Etiquetas:** cada campo de formulario tiene su `<label>` asociado; los obligatorios se marcan con "
        "asterisco y una nota.",
        "**Teclado:** todas las acciones se pueden hacer con teclado, con foco visible en los campos.",
        "**Estado en texto:** los estados (ENTREGADO, RECHAZADO, sede no disponible, cadena ÍNTEGRA o ALERTA) "
        "se escriben con palabras y no se comunican solo por color.",
        "**Diseño adaptable:** las vistas se reacomodan hasta 390 px de ancho" + ref("movil") + ".",
        "**Mínimo privilegio visible:** cada rol solo ve sus opciones de menú; el acceso directo a una ruta no "
        "permitida muestra un error 403 claro" + ref("403") + ".",
    ])
    w.p("Estos criterios se aplicaron y se revisaron manualmente sobre las plantillas finales; no se corrió "
        "una herramienta automática de auditoría de accesibilidad.")


def s_prototipo(w, img):
    w.p("El prototipo funcional es la versión v2 de la plataforma. Se probó en una máquina virtual **Kali "
        "Linux** en VirtualBox con 3,8 GB de RAM, Docker 28 y Compose v2, con el comando "
        "`docker compose down -v && docker compose up -d --build`. HAPI FHIR tarda entre 85 y 95 s en "
        "responder después del arranque. Los puertos se pueden reasignar en `.env` si el anfitrión ya los "
        "usa. Los pasos de ejecución están en el README y en el Anexo E.")
    w.tabla(["Requisito", "Criterio de aceptación", "Estado", "Evidencia"], [
        ["RF1 Ingesta", "HL7 v2 y CSV (y JSON) de las 3 sedes", "Cumplido", "`/hsb/hl7`, `/hsb/csv?sede=N`, "
         "`/hsb/json?sede=N`; ejemplos 01–04 y mensaje de 57 campos"],
        ["RF2 FHIR R4", "Patient, Encounter, Observation y Condition (CIE-10) en Bundle", "Cumplido",
         "`fhir/normalizer.py`; Bundle de 1001 con 26 recursos y 0 errores en `$validate`"],
        ["RF3 HSB", "Enrutamiento por sede, transformación, validación, reintentos, idempotencia", "Cumplido",
         "`hsb/`; con HAPI apagado, entregado tras 7 intentos sin duplicar"],
        ["RF4 Datos distribuidos", "Un nodo por sede y consulta unificada", "Cumplido, con motores distintos",
         "`pg_sede1`, `mongo_sede2`, `pg_sede3`; `db/consulta_unificada.py`"],
        ["RF5 Seguridad", "Token, roles y auditoría encadenada", "Cumplido (Fabric no)", "`app/auth.py`, "
         "`app/rbac.py`, `app/audit.py`, `app/usuarios.py`, `pg_central`" + ref("403")],
        ["RF6 Vistas", "Paciente, Admisionista, Médico, Reporte de HC con tablero", "Cumplido (más panel de "
         "administración)", "`app/main.py`, `app/templates/`; Figuras de la sección de interfaces"],
        ["RNF Un comando", "`docker compose up` levanta todo", "Cumplido", "HAPI responde a los 85–95 s"],
        ["RNF Sede caída", "La vista sigue con las otras dos y marca la sede", "Cumplido",
         "`docker stop mongo_sede2`" + ref("caida1")],
        ["RNF Observabilidad", "`/health` y `/metrics` en cada servicio", "Cumplido en HSB y API", "HAPI no "
         "tiene `/health` propio; su estado lo reportan el HSB y la API"],
    ], anchos=[2.6, 4.2, 2.6, 5.6], titulo="Matriz de criterios de aceptación frente a RF1–RF6 y requisitos no "
       "funcionales.", tam=8.5)
    w.sub("Evidencias de aceptación")
    w.p("Un usuario con un rol que no tiene permiso para una vista recibe un error 403 y el intento queda en "
        "la auditoría" + ref("403") + ".")
    if "17_acceso_denegado_403.png" in img:
        FIGS["403"] = w.figura(img["17_acceso_denegado_403.png"], "Acceso denegado (403) al abrir una vista no "
                               "permitida para el rol; el intento queda auditado.", alto_max_cm=9)
    caida = [("caida1", "19_reporte_incompleto_sede2_caida.png", "Con `docker stop mongo_sede2`, el Reporte de "
              "HC responde con las sedes 1 y 3, marca la Sede 2 como no disponible y el reporte como incompleto."),
             ("caida2", "20_panel_sede2_caida.png", "Panel durante la caída: 2 de 3 sedes activas y la Sede 2 "
              "(MongoDB) caída."),
             ("alterada", "21_auditoria_alterada_detectada.png", "Después de un `UPDATE` manual en "
              "`evento_auditoria`, el verificador pasa a ALERTA y señala el primer evento alterado.")]
    if any(f in img for _, f, _ in caida):
        w.p("Las siguientes capturas muestran la prueba de caída de la sede MongoDB y la detección de una "
            "alteración en la cadena de auditoría.")
        for clave, f, pie in caida:
            if f in img:
                FIGS[clave] = w.figura(img[f], pie)


def s_resultados(w, img, evid):
    w.h("Pruebas funcionales en vivo")
    w.p("Las mediciones se hicieron en Kali Linux (VirtualBox, 3,8 GB de RAM, Docker 28) el 10 y 11 de "
        "noviembre de 2026, sobre un arranque limpio y con los mensajes oficiales del docente "
        "(`ejemplos/`)." + (" Las salidas de consola están en el Anexo C." if evid else ""))
    w.tabla(["Prueba", "Resultado medido"], [
        ["Arranque limpio (`down -v && up -d --build`)", "Todos los contenedores arriba; HAPI responde a los "
         "85–95 s"],
        ["Cobertura FHIR antes de enviar mensajes", "0 % en las 3 sedes"],
        ["Ejemplo 01 (ADT^A01, sede 2 MongoDB)", "Entregado"],
        ["Ejemplo 01 reenviado", "`duplicado`; exactamente 1 Patient 1007 en HAPI y 1 documento en MongoDB"],
        ["Ejemplo 02 (ORU^R01, sede 1 PostgreSQL)", "Entregado; Observation 718-7 = 13,8 g/dL"],
        ["Ejemplo 03 (inválido)", "Rechazado con 3 motivos"],
        ["Ejemplo 04 (CSV, sede 3)", "3 entregados (1008, 1009, 1010) y 2 rechazados"],
        ["Mensaje HL7 de 57 campos (`06_adt_a03_57_campos_sede1.hl7`)", "11 recursos FHIR; 56 de 57 campos; "
         "100 % de obligatorios (falta solo el 42, diagnóstico de muerte, porque el paciente sale vivo)"],
        ["Cobertura FHIR por sede después de los ejemplos", "Sede 1: 50 % → 67 % (tras el mensaje de 57 "
         "campos); sede 2: 33,3 %; sede 3: 75 %"],
        ["Consulta unificada del paciente 1001 (3 sedes, 2 motores)", "52 de 57 campos; 100 % de obligatorios"],
        ["Bundle de 1001 en HAPI `$validate`", "26 recursos (3 Organization, 3 Practitioner, 1 Patient, 3 "
         "Encounter, 7 Condition, 5 Observation, 3 MedicationRequest, 1 AllergyIntolerance); 0 errores, 33 "
         "advertencias, 46 mensajes informativos"],
        ["Consulta unificada de 1001 (evidencia del 11 nov.)", "`reporte_completo = true`; latencia por sede: "
         "74,8 ms (PostgreSQL), 83,6 ms (MongoDB), 37,9 ms (PostgreSQL)"],
        ["HAPI apagado al enviar un mensaje", "Respuesta `reintentando`; 7 intentos con esperas de 2 a 64 s; "
         "entregado solo al volver HAPI, 129,5 s (10 nov.) y 132,0 s (11 nov.) después del primer intento; "
         "sin duplicado"],
        ["HAPI apagado más que la ventana de reintentos", "MUERTO tras 7 intentos (Superó 7 intentos); con "
         "HAPI de nuevo arriba, `POST /hsb/reencolar` lo entregó en 1 intento (2 607 ms)"],
        ["Reenvío de 01, 03 y del CSV (11 nov.)", "01: `duplicado`, 1 solo Patient 1007 en HAPI; 03: rechazado "
         "con 3 motivos; CSV: 3 duplicados y 2 rechazados"],
        ["`docker stop mongo_sede2`", "La consulta responde con sedes 1 y 3, `reporte_completo = false`, "
         "`/health` DEGRADED 2/3; se recupera al iniciar el contenedor"],
        ["`UPDATE evento_auditoria … WHERE indice = 3`", "El verificador señala el índice 3: \"Alteración de "
         "contenido\""],
        ["Paciente pide la historia de otro paciente", "403 y evento `ACCESO_DENEGADO`"],
        ["ACID en PostgreSQL (`db/demo_acid.sql`)", "Violación de `CHECK` en `clasificacion_triage` → rollback "
         "completo, sin usuario huérfano"],
        ["Reinicio del bus con mensajes pendientes", "Recuperó 2 mensajes pendientes y los entregó"],
        ["Pruebas automatizadas", "44 de 44 pasan (8,78 s)"],
    ], anchos=[6.2, 8.8], titulo="Resultados medidos en las pruebas en vivo.", tam=8.5)
    w.p("Los ejemplos 01 (dos veces), 02, 03 y las 5 filas del CSV son 9 mensajes recibidos: 5 entregados, "
        "1 duplicado y 3 rechazados. Los 3 rechazos son los que el contrato de `ejemplos/LEEME.md` exige "
        "rechazar; ningún mensaje válido quedó MUERTO en el flujo normal.")
    if "14b_reporte_1001_cobertura_y_sello.png" in img or "15_reporte_1020_cobertura.png" in img:
        w.p("La cobertura de campos se ve en el Reporte de HC: el paciente 1001 reúne 52 de 57 campos desde las "
            "tres sedes" + ref("cob1001") + " y el paciente 1020, con el mensaje de 57 campos, llega a 56 de "
            "57" + ref("cob1020") + ".")
        if "14b_reporte_1001_cobertura_y_sello.png" in img:
            FIGS["cob1001"] = w.figura(img["14b_reporte_1001_cobertura_y_sello.png"], "Reporte del paciente 1001 "
                                       "(fragmentos): 52 de 57 campos, 23 de 23 obligatorios, campos faltantes "
                                       "y código de verificación del reporte.")
        if "15_reporte_1020_cobertura.png" in img:
            FIGS["cob1020"] = w.figura(img["15_reporte_1020_cobertura.png"], "Reporte del paciente 1020 "
                                       "(fragmentos): 56 de 57 campos y 100 % de obligatorios; solo falta el "
                                       "campo 42 (diagnóstico de muerte).")

    w.h("Indicadores operativos del bus")
    w.p("La guía pide reportar latencia, mensajes por minuto, porcentaje de fallidos y cobertura. Para las "
        "capturas se cargaron los ejemplos oficiales y el generador de datos sintéticos con 60 pacientes: 148 "
        "mensajes, de los que 135 se entregaron, 8 se rechazaron a propósito y 5 eran reenvíos (duplicados). "
        "La tabla recoge dos lecturas del 11 de noviembre de 2026: el panel a las 05:19" + ref("p_res") +
        " y el endpoint `/metrics` del HSB a las 05:22 (Anexo C), después de reenviar los ejemplos 01, 03 y el "
        "CSV.")
    w.tabla(["Indicador", "Panel (05:19)", "`/metrics` (05:22)", "Lectura"], [
        ["Mensajes recibidos", "157", "166", "La diferencia incluye los reenvíos de 01, 03 y las 5 filas CSV"],
        ["Entregados", "141", "143", "Los reenvíos no generan entregas nuevas"],
        ["Rechazados", "11", "14", "Todos son errores introducidos a propósito en los datos de prueba"],
        ["Duplicados detectados", "5", "9", "Idempotencia: el ejemplo 01 y las 3 filas válidas del CSV"],
        ["Mensajes muertos", "0", "0", "Ningún mensaje válido quedó MUERTO en el flujo normal"],
        ["Porcentaje de fallidos", "7,2 %", "8,92 %", "Rechazados sobre mensajes no duplicados (14 de 157)"],
        ["Latencia media", "372,3 ms", "369,87 ms", "Promedio por mensaje entregado en la sesión"],
        ["Mensajes en el último minuto", "53", "7", "Ventana móvil: depende del momento de la lectura"],
        ["Cobertura FHIR global", "95,5 % (85 de 89 pacientes)", "—", "Por sede en la pestaña de estado: "
         "96,6 %, 92,9 % y 97,0 %" + ref("estado")],
        ["Recursos en HAPI", "438", "—", "64 Patient, 103 Encounter, 172 Condition, 40 Observation, 40 "
         "MedicationRequest, 11 AllergyIntolerance, 5 Practitioner, 3 Organization" + ref("p_fhir")],
    ], anchos=[3.6, 2.8, 2.4, 6.2], titulo="Indicadores operativos del bus en dos lecturas de la misma sesión.",
        tam=8.5)
    w.p("**Lo que no se midió.** Estos valores son contadores en memoria de una sesión de demostración, no una "
        "prueba de carga: no se midió de forma sistemática la latencia por mensaje ni el número máximo de "
        "mensajes por minuto que soporta el bus. Por eso se reportan como observación y no como capacidad del "
        "sistema.")

    w.h("Discusión")
    w.vinetas([
        "**Idempotencia frente a coordinación.** El reintento con HAPI apagado confirma que la idempotencia es "
        "lo que hace seguro repetir: 7 intentos, una sola entrega y ningún duplicado, sin coordinación "
        "distribuida (2PC). Esto coincide con los patrones de receptor idempotente y canal de mensajes "
        "muertos de Hohpe y Woolf (2003).",
        "**Disponibilidad frente a consistencia.** Con la sede MongoDB detenida, la consulta siguió respondiendo "
        "y marcó el reporte como incompleto. Es la elección AP descrita en el marco teórico: se acepta un "
        "reporte parcial y declarado a cambio de no detener la atención (Tanenbaum y Van Steen, 2017).",
        "**Cobertura de campos.** La cobertura muestra el límite de los datos y no del traductor: el mensaje "
        "completo llega a 56 de 57; la historia real de 1001 llega a 52 de 57 porque sus atenciones no traen "
        "todos los campos opcionales.",
        "**Cobertura FHIR por sede.** No llega al 100 %, porque se mide como pacientes con recurso en HAPI sobre "
        "pacientes de la sede, y los pacientes sembrados como legados solo se enlazan cuando llega un mensaje "
        "suyo. La guía pide 0 % antes y 100 % después de migrar; falta un paso de migración que reenvíe a "
        "todos los pacientes existentes por el bus.",
        "**Validación FHIR.** Las 33 advertencias de `$validate` se deben a que el proyecto usa extensiones y "
        "sistemas de códigos propios que HAPI no puede resolver; no son errores de estructura. Las "
        "experiencias de Chile y Argentina usan perfiles nacionales para evitar esto (Centro Nacional en "
        "Sistemas de Información en Salud, 2022; Ministerio de Salud de la Nación Argentina, 2020).",
        "**Frente a las herramientas del estado del arte.** Un bus propio cubrió los requisitos con un flujo "
        "corto y probado, pero no ofrece lo que traen Mirth Connect u OpenHIM: canales gráficos, conectores "
        "ya hechos y una consola de mediación. Para una red real ese costo de construir y mantener pesaría "
        "más que en un parcial.",
    ])


def s_conclusiones(w, img):
    w.numerada([
        "Se puede unificar la historia de tres sedes **sin reemplazar sus legados ni igualar sus motores**: un "
        "registro canónico de 57 campos y un repositorio con una sola interfaz bastaron para tratar PostgreSQL "
        "y MongoDB igual desde el bus y la consulta.",
        "Elegir disponibilidad en la lectura (AP) mantuvo la consulta en marcha con una sede caída, a cambio de "
        "un reporte marcado como incompleto.",
        "Identificadores deterministas, `PUT` en FHIR y UPSERT en las sedes hicieron idempotente la entrega; "
        "con eso, los reintentos y la recuperación tras un reinicio no necesitan transacción distribuida.",
        "Separar la auditoría y las cuentas en `pg_central` permitió apagar cualquier sede sin perder la "
        "trazabilidad, y demostrar la detección de una alteración hecha directamente en la base.",
        "Validar los permisos en la API, con administradores limitados a su sede y cuentas de paciente con "
        "contraseña temporal, llevó el control de acceso del prototipo más allá de los cuatro roles mínimos.",
    ])
    w.h("Limitaciones")
    w.vinetas([
        "MongoDB corre sin *replica set*: sin transacciones multi-documento ni conmutación por fallo. Además, "
        "`guardar` lee el documento y lo reemplaza; dos escrituras simultáneas sobre el mismo paciente podrían "
        "pisarse (no hay control de concurrencia optimista).",
        "Una sola instancia de HAPI FHIR, con su base embebida por defecto.",
        "Los segmentos Z (`ZPI`, `ZPV`, `ZRX`, `ZEG`) son una convención del proyecto, no un estándar nacional; "
        "los códigos REPS son sintéticos y las extensiones FHIR usan URL propias, no perfiles publicados.",
        "Cobertura FHIR por sede sin paso de migración de los pacientes existentes.",
        "Latencia y mensajes por minuto no medidos con una prueba de carga.",
        "Los endpoints del HSB (`:8001`) no exigen autenticación; solo la API la exige.",
        "Las cuentas semilla tienen contraseñas de prueba documentadas y el secreto JWT es de desarrollo si no "
        "se cambia en `.env`.",
        "No hay pipeline de CI/CD.",
    ])
    w.h("Trabajo futuro")
    w.vinetas([
        "*Replica set* de MongoDB y control de versión del documento para escrituras concurrentes.",
        "Script de migración que pase a todos los pacientes legados por `/hsb/json` (cobertura FHIR del 100 %).",
        "Prueba de carga para medir latencia, mensajes por minuto y porcentaje de fallidos.",
        "Keycloak u otro proveedor OIDC, TLS entre servicios y autenticación en el HSB.",
        "Anclaje periódico de la cadena de auditoría en Hyperledger Fabric; Prometheus y Grafana.",
        "Pipeline de integración continua que corra las 44 pruebas en cada cambio.",
    ])


def s_referencias(w, img):
    for r in REFERENCIAS:
        w.p(r, alinear="left", sangria_fr=1.27, despues=8)


def s_anexos(w, img, evid):
    w.h("Anexo A. Código clave")
    w.tabla(["Archivo", "Qué contiene"], [
        ["`traductor/catalogo_57.py`", "Catálogo de los 57 campos (HL7, CSV, PostgreSQL, MongoDB, FHIR)"],
        ["`traductor/dominios.py`", "Dominios de la Res. 866 y sinónimos por sede"],
        ["`traductor/traductor.py`", "Traducciones al y desde el registro canónico, derivados y cobertura"],
        ["`fhir/normalizer.py`", "Registro canónico → Bundle FHIR R4"],
        ["`hsb/ingesta.py`, `hsb/queue_manager.py`, `hsb/main.py`", "Flujo del bus, cola de reintentos, endpoints"],
        ["`hsb/validator.py`", "Reglas de validación antes de transformar"],
        ["`db/repositorio.py`, `db/consulta_unificada.py`", "Repositorios PostgreSQL y MongoDB; consulta en "
         "paralelo"],
        ["`db/schema.sql`, `db/sede2/init-mongo.js`, `db/central/init.sql`", "Esquemas y datos sintéticos"],
        ["`app/main.py`, `app/rbac.py`, `app/audit.py`", "API, permisos por rol, auditoría encadenada"],
        ["`app/usuarios.py`", "Cuentas en `pg_central`, PBKDF2, administradores por sede, cuenta del paciente"],
        ["`app/dashboard.py`, `app/templates/`", "Panel de administración, tablero y vistas"],
        ["`scripts/generar_datos_prueba.py`", "Generador de pacientes sintéticos enviados por el bus"],
    ], anchos=[6.5, 8.5], titulo="Archivos de código clave.")

    w.h("Anexo B. Pruebas automatizadas")
    w.p("Las 44 pruebas (Tabla de pruebas por suite en Proceso de desarrollo) se ejecutan sin Docker:")
    w.codigo(["pip install -r hsb/requirements.txt -r app/requirements.txt pytest",
              "python -m pytest tests/ -v",
              "...",
              "44 passed"])
    w.p("Mensaje HL7 de prueba con los 57 campos: `tests/datos/06_adt_a03_57_campos_sede1.hl7`. Guion de la "
        "demostración en vivo: `docs/guion_demostracion.md`; guía para Kali Linux: `docs/guia_kali_linux.md`.")

    w.h("Anexo C. Evidencias de ejecución")
    if evid:
        w.p("Extractos de las salidas de consola tomadas en vivo sobre la plataforma desplegada. Los archivos "
            "completos están en `docs/evidencias/`.")
        for nombre, lineas in evid:
            w.p(f"**{nombre}**", alinear="left", despues=2, mantener=True)
            w.codigo(lineas, tam=7.5)
    else:
        w.p("Las pruebas en vivo se describen en la tabla de Resultados y se reproducen con los comandos del "
            "Anexo E y del guion de demostración (`docs/guion_demostracion.md`).")

    w.h("Anexo D. Usuarios de prueba")
    w.p("Todos los datos son sintéticos. Las contraseñas son de prueba y están documentadas en el README.")
    w.tabla(["Usuario", "Contraseña", "Rol", "Qué puede hacer"], [
        ["`paciente_carlos`", "`Paciente123!`", "paciente", "Su historia (documento 1001), su Bundle FHIR y quién "
         "accedió a su historia"],
        ["`admision_laura`", "`Admision123!`", "admisionista", "Buscar en qué sedes existe un paciente, admitir "
         "con triage, ver envíos al bus. No ve diagnósticos"],
        ["`medico_mateo`", "`Medico123!`", "médico", "Historia unificada; diagnóstico, fórmula y egreso con sello"],
        ["`auditor_elena`", "`Auditor123!`", "auditor", "Reporte de HC, estado de la plataforma, verificador; "
         "panel en modo consulta"],
        ["`admin_plataforma`", "`Admin123!`", "administrador", "Panel de administración y usuarios de toda la red"],
        ["`admin_sincelejo`, `admin_cartagena`, `admin_corozal`", "`Admin123!`", "administrador de sede",
         "Panel; crea y gestiona médicos, admisionistas y pacientes de su sede"],
        ["Documento del paciente admitido", "Temporal (se muestra una vez)", "paciente", "Portal del paciente; "
         "debe cambiar la contraseña en el primer ingreso"],
    ], anchos=[4.2, 2.8, 2.6, 5.4], titulo="Usuarios de prueba.", tam=8.5)

    w.h("Anexo E. Cómo ejecutar")
    w.codigo([
        "cp .env.example .env",
        "docker compose down -v && docker compose up -d --build",
        "docker compose ps        # HAPI tarda unos 90 s en responder",
        "",
        "# Vistas: http://localhost:8000   HSB: http://localhost:8001   HAPI: http://localhost:8090/fhir",
        "",
        "# Ejemplos oficiales",
        "curl -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 http://localhost:8001/hsb/hl7",
        "curl -X POST --data-binary @ejemplos/02_oru_r01_laboratorio_sede1.hl7 http://localhost:8001/hsb/hl7",
        "curl -X POST --data-binary @ejemplos/03_adt_a01_invalido.hl7 http://localhost:8001/hsb/hl7",
        "curl -X POST --data-binary @ejemplos/04_sede3_legado.csv \"http://localhost:8001/hsb/csv?sede=3\"",
        "",
        "# Datos sintéticos masivos",
        "python3 scripts/generar_datos_prueba.py --pacientes 80",
        "",
        "# Reintento: HAPI caído",
        "docker compose stop hapi-fhir   # enviar un mensaje, luego:",
        "docker compose start hapi-fhir  # el bus lo entrega solo",
        "",
        "# Caída de una sede",
        "docker stop mongo_sede2         # luego: docker start mongo_sede2",
        "",
        "# Alteración de la auditoría",
        "docker exec -it pg_central psql -U clinica_user -d clinica_central \\",
        "  -c \"UPDATE evento_auditoria SET usuario_sistema='intruso' WHERE indice = 3\"",
        "",
        "# ACID en PostgreSQL",
        "docker exec -i pg_sede1 psql -U clinica_user -d clinica_sincelejo < db/demo_acid.sql",
    ])

    w.h("Anexo F. Uso declarado de inteligencia artificial")
    w.tabla(["Etapa", "Herramienta", "Uso", "Revisión humana"], [
        ["Fases 1 a 5 (v1)", "Antigravity (Google DeepMind)", "Código Mermaid de los diagramas, estructura del "
         "repositorio, esquemas SQL, normalizador, parsers, validador, plantillas, pruebas y borradores de los "
         "informes", "Revisión de coherencia de los diagramas, verificación de los 4 ejemplos oficiales, "
         "pruebas de 403, alteración y caída de sede"],
        ["Mejora v2", "Claude Code (Anthropic)", "Traductor de 57 campos, adaptador MongoDB, cola de reintentos, "
         "auditoría persistente, panel de administración, gestión de usuarios, vistas, generador de datos y "
         "pruebas", "Pruebas en vivo en Kali Linux con Docker (ejemplos, duplicado, reintento, caída de sede, "
         "alteración, `$validate`) y 44 pruebas automatizadas"],
        ["Imagen de portada del inicio de sesión", "Asistente ATLAS", "Generación de la imagen", "Selección por "
         "los integrantes"],
    ], anchos=[2.8, 3, 5.2, 4], titulo="Uso declarado de IA (detalle en `docs/bitacora.md`).", tam=8.5)
    w.p("Código abierto usado: FastAPI, Uvicorn, HTTPX, Jinja2, PostgreSQL, MongoDB y PyMongo, HAPI FHIR "
        "(Apache 2.0), Docker Compose. Cada integrante debe poder explicar y modificar en vivo lo que entregó.")


def s_avance_inicial(w, img):
    w.p("Estado de los entregables de la Fase 1 (análisis, UML y diseño), entregada el 8 de noviembre de 2026, "
        "y su actualización en la versión 2:")
    w.vinetas([
        "**Repositorio y estructura base:** repositorio Git con commits de ambos integrantes desde la Fase 1, "
        "estructura de carpetas (`app/`, `hsb/`, `fhir/`, `db/`, `tests/`, `ejemplos/`, `docs/`, `infra/`), "
        "`README.md`, `.env.example` y `docker-compose.yml`. Completo.",
        "**Cuatro diagramas UML en Mermaid** (casos de uso, secuencia, clases y estados del mensaje) con tablas "
        "de coherencia entre ellos. Completo; actualizados a la v2 (MongoDB, traductor, cuentas).",
        "**Arquitectura y justificación de componentes:** diagrama de arquitectura y tabla componente / "
        "requisito / alternativas / razón. Completo; actualizado a siete contenedores.",
        "**Mapeo de campos:** tabla de la Fase 1 con 24 filas representativas (mínimo exigido: 15) y, en la v2, "
        "el mapeo completo de los 57 campos generado desde el catálogo (`docs/mapeo_57_campos.md`).",
        "**Entorno Docker:** esqueleto de `docker-compose.yml` en la Fase 1; en la v2, siete contenedores que "
        "arrancan con un solo comando.",
        "**Marco teórico y pregunta de autoevaluación** de la Fase 1 (sede 2 caída: el médico ve la historia "
        "parcial con aviso). Completo.",
        "**Pendiente de la Fase 1:** la evidencia de ejecución del repositorio de referencia del docente quedó "
        "marcada como pendiente en el informe de esa fase.",
    ])


def s_viab_intro(w, img):
    w.p("Esta sección distingue lo que el prototipo implementa y se probó de lo que se propone para una "
        "operación real en la red de IPS.")


def s_escalabilidad(w, img):
    w.p("Se marca con **[Implementado]** lo que existe y se probó, y con **[Propuesto]** lo que no se "
        "implementó.")
    w.vinetas([
        "**[Implementado]** Siete contenedores con Docker Compose; cada uno puede caer sin detener a los demás "
        "(se probó con `mongo_sede2` y `hapi-fhir`).",
        "**[Implementado]** Consulta unificada en paralelo: una sede caída cuesta su tiempo de espera (3 s), no "
        "se suma al de las otras.",
        "**[Implementado]** Cola de reintentos en segundo plano con estado persistido en cada sede.",
        "**[Implementado, sin evidencia de ejecución]** Manifiestos de Kubernetes para Minikube en `infra/k8s/`.",
        "**[Propuesto]** Réplicas del HSB detrás de un balanceador y un broker (Kafka o RabbitMQ) particionado "
        "por sede; autoescalado por tamaño de cola.",
        "**[Propuesto]** Réplicas de lectura en PostgreSQL; *replica set* en MongoDB; Citus si una sede crece a "
        "millones de atenciones; HAPI sobre PostgreSQL y en más de una instancia.",
        "**[Propuesto]** Prometheus y Grafana sobre los `/metrics` existentes; prueba de carga.",
    ])
    w.tabla(["Aspecto", "Implementado", "Propuesto (no implementado)"], [
        ["Ingesta", "Un HSB con cola en hilo de segundo plano y estado en las bases", "Réplicas del HSB y broker "
         "particionado por sede"],
        ["Datos", "2 PostgreSQL y 1 MongoDB, cada uno un nodo único", "Réplicas de lectura; *replica set*; Citus"],
        ["FHIR", "Una instancia de HAPI con su base embebida", "HAPI sobre PostgreSQL y varias instancias"],
        ["Seguridad", "JWT HS256, roles, cuentas PBKDF2 en `pg_central`", "Keycloak/OIDC, TLS entre servicios, "
         "autenticación en el HSB"],
        ["Auditoría", "Cadena SHA-256 en `pg_central`", "Anclaje en Hyperledger Fabric (bonus no hecho)"],
        ["Despliegue", "Docker Compose; manifiestos para Minikube", "Autoescalado del HSB por tamaño de cola"],
    ], anchos=[2.4, 6.2, 6.4], titulo="Viabilidad técnica: implementado frente a propuesto.")
    w.p("**Qué escalar primero ante 100 veces más mensajes:** el HSB. Hoy hace el primer intento de entrega de "
        "forma síncrona y tiene un solo hilo de reintentos por proceso. Lo primero sería poner un broker "
        "delante para responder `202` de inmediato y repartir el trabajo entre varias réplicas del HSB; luego "
        "HAPI (más instancias sobre PostgreSQL) y por último las bases de cada sede.")


def s_cumplimiento(w, img):
    w.vinetas([
        "**[Implementado]** Solo datos sintéticos, también los códigos REPS de prestador.",
        "**[Implementado]** Ley 1581 de 2012: el paciente ve quién accedió a su historia, con qué rol y cuándo "
        "(acceso y finalidad); el admisionista no ve datos clínicos (mínimo privilegio); la auditoría "
        "encadenada impide reescribir sin dejar rastro.",
        "**[Implementado]** Resolución 866 de 2021: los 57 campos están en el catálogo y se mide su cobertura "
        "por paciente con la lista de faltantes.",
        "**[Implementado]** Contraseñas PBKDF2-SHA256 con sal por usuario; contraseña temporal con cambio "
        "obligatorio; cada alta, desactivación o restablecimiento queda auditado.",
        "**[Propuesto]** TLS entre servicios, cifrado de las bases en reposo y gestión de secretos.",
        "**[Propuesto]** Proveedor de identidad (Keycloak/OIDC) y autenticación en los endpoints del HSB.",
        "**[Propuesto]** Registro del consentimiento del paciente (recurso FHIR Consent) y políticas de "
        "retención de la historia clínica.",
    ])


def s_interop_intro(w, img):
    w.p("La interoperabilidad no se limita a mover mensajes: los datos deben llegar con el mismo significado, "
        "completos y trazables. Esta sección describe cómo la plataforma trata cada dimensión. Los pilares "
        "técnico y semántico se demostraron; el organizacional solo se menciona, porque el gobierno de datos "
        "se evalúa en el curso de Arquitectura TI.")


def s_io_calidad(w, img):
    w.vinetas([
        "**Modelo canónico de 57 campos** (`traductor/catalogo_57.py`): un único catálogo define origen, "
        "destino, obligatoriedad y dominio de cada campo; las tres sedes se traducen contra él.",
        "**Validación antes de transformar** (`hsb/validator.py`): documento, nombre, sexo, sede, fechas, CIE-10 "
        "y LOINC; un mensaje inválido se rechaza con todos sus motivos y no llega a FHIR.",
        "**Cobertura medida:** por paciente (campos con valor sobre 57 y obligatorios sobre 23, con la lista de "
        "faltantes) y por sede (pacientes con recurso en HAPI).",
        "**Unicidad e idempotencia:** identificadores deterministas en FHIR y llaves de UPSERT en las sedes; la "
        "búsqueda de admisión detecta datos distintos del mismo documento entre sedes (posible duplicado).",
        "**Trazabilidad:** estado de cada mensaje en `mensaje_bus` de su sede y eventos de acceso en la cadena "
        "de auditoría.",
    ])


def s_io_semantica(w, img):
    w.vinetas([
        "**CIE-10** en `Condition.code` para los diagnósticos 33 a 39 y **LOINC** en `Observation.code` para "
        "laboratorio.",
        "**Tabla de terminología** `ejemplos/05_ref_terminologia.csv`: convierte los textos locales del CSV de "
        "la sede 3 a CIE-10; lo que no se puede mapear se rechaza con motivo.",
        "**Dominios con sinónimos** (`traductor/dominios.py`): tipo de documento, entorno, vía de ingreso, "
        "triage, condición de salida, entre otros, de modo que `E` (HL7), `EMER` o `01` significan lo mismo.",
        "**Extensiones FHIR propias** para los campos de la Res. 866 sin lugar en el recurso base (no se usó un "
        "perfil nacional publicado).",
        "**No implementado:** servidor de terminología, ConceptMap y ValueSet de FHIR; se proponen como trabajo "
        "futuro.",
    ])
    w.p("Ejemplo de un campo de punta a punta, el **14, municipio de residencia (código DANE)**:")
    w.tabla(["Paso", "Representación"], [
        ["HL7 v2", "`PID-11.9` (noveno componente de la dirección), por ejemplo `70001`"],
        ["Registro canónico", "`usuario.municipio_residencia = \"70001\"`"],
        ["PostgreSQL (sedes 1 y 3)", "`usuario.municipio_residencia VARCHAR(5)`"],
        ["MongoDB (sede 2)", "`pacientes.residencia.municipio_dane`"],
        ["FHIR R4", "`Patient.address[0].district`"],
    ], anchos=[4.5, 10.5], titulo="Recorrido del campo 14 por los cinco formatos.")


def s_io_tecnica(w, img):
    w.vinetas([
        "**Entradas:** HL7 v2 en texto por HTTP POST (ADT^A01, ADT^A03, ORU^R01 y RDE^O11 en sus segmentos de "
        "medicamento), CSV legado con `;` y JSON de las vistas.",
        "**Segmentos Z** `ZPI`, `ZPV`, `ZRX` y `ZEG` para los datos de la Res. 866 que HL7 v2.5 no trae.",
        "**Salida estándar:** FHIR R4 por REST en JSON, con Bundle `transaction` y `PUT` de identificadores "
        "deterministas; validación con `$validate` de HAPI.",
        "**Dos motores de base** con modelos distintos (relacional y documental) integrados mediante el "
        "registro canónico y el repositorio con interfaz única.",
        "**Desacople:** las vistas y los legados no comparten base; todo pasa por el HSB y la API. Cada servicio "
        "expone `/health` y `/metrics`.",
        "**No implementado:** suscripciones FHIR, perfiles IHE y mensajería asíncrona con broker.",
    ])


def s_io_gobernanza(w, img):
    w.p("Solo se menciona, como pide la guía. En una red real harían falta acuerdos entre las IPS sobre:")
    w.vinetas([
        "La definición y el versionado de los segmentos Z, los códigos locales y la tabla de terminología.",
        "Los roles y sus permisos: qué ve cada perfil (en el prototipo, paciente, admisionista, médico, auditor "
        "y administrador general o de sede).",
        "La revisión periódica de la auditoría y de los accesos a la historia clínica.",
        "El cumplimiento de la Ley 1581 de 2012 (autorización, finalidad, acceso) y la custodia de los datos.",
    ])


def s_io_herr_tecnica(w, img):
    w.vinetas([
        "**HAPI FHIR R4 7.2.0** (código abierto, Java): **usado** como servidor FHIR; recibe los Bundles "
        "`transaction` y valida con `$validate`.",
        "**HSB propio en FastAPI** (Python): **usado** como bus; traducción, validación, cola, reintentos e "
        "idempotencia.",
        "**Mirth Connect** (NextGen Healthcare, 2023): **evaluado, no usado**; motor HL7 con canales gráficos. "
        "Se descartó por agregar otra plataforma Java y una configuración que el equipo no podía modificar "
        "en vivo con la misma soltura.",
        "**OpenHIM** (OpenHIE Consortium, 2022): **evaluado, no usado**; su idea de separar la mediación "
        "(seguridad, auditoría) del almacenamiento sí se aplicó con `pg_central`.",
        "**Apache Camel**: **evaluado, no usado**; marco de integración en Java con componentes HL7 y FHIR.",
        "**Docker Compose**: **usado** para el despliegue de un comando.",
    ])


def s_io_herr_semantica(w, img):
    w.vinetas([
        "**Catálogo y dominios propios** (`catalogo_57.py`, `dominios.py`): **usados** para normalizar los "
        "valores de la Res. 866.",
        "**Tabla de terminología del docente** (`05_ref_terminologia.csv`): **usada** para mapear los textos locales a CIE-10.",
        "**Validador con expresiones regulares** para el formato de CIE-10 y LOINC: **usado**. Verifica el "
        "formato del código, no su existencia en el catálogo oficial.",
        "**Servidores de terminología** (por ejemplo, el módulo de terminología de HAPI con ValueSet y "
        "ConceptMap): **no usados**; se proponen para validar que cada código exista.",
    ])


def s_io_compat(w, img):
    w.p("La matriz resume la compatibilidad de herramientas de integración con los estándares HL7 v2.x, HL7 "
        "CDA, HL7 FHIR y perfiles IHE. Las filas de herramientas de terceros provienen de la comparación de "
        "referencia de la plantilla del curso y no fueron verificadas por el equipo; la última fila describe "
        "la plataforma de este proyecto. Símbolos: ✔ soporte nativo, ◑ parcial, ✖ no soportado.")
    S, P, N = "✔", "◑", "✖"
    w.tabla(["Herramienta", "HL7 v2.x", "HL7 CDA", "HL7 FHIR", "IHE perfiles"], [
        ["HAPI FHIR Server", N, N, S, P],
        ["Smile CDR", S, S, S, S],
        ["Mirth Connect", S, S, S, P],
        ["OpenHIM", S, P, S, S],
        ["Apache Camel + camel-fhir", S, P, S, P],
        ["Kong API Gateway", N, N, S, N],
        ["Redox (SaaS)", S, S, P, N],
        ["Rhapsody Integrator", S, S, S, S],
        ["GCP Healthcare API / Azure HDS", S, P, S, N],
        ["Snowstorm", N, N, S, N],
        ["Ontoserver", N, N, S, N],
        ["Apelon DTS", N, N, P, N],
        ["**Plataforma de este proyecto (HSB propio)**", f"{S} ADT^A01, ADT^A03, ORU^R01; RDE^O11 parcial",
         N, f"{S} R4, Bundle transaction", N],
    ], anchos=[4.6, 3.6, 2, 2.8, 2], titulo="Compatibilidad de herramientas de integración con los estándares "
       "de interoperabilidad en salud.", tam=8.5, centrar_cols=(1, 2, 3, 4))
    w.p("**Observaciones.** La plataforma cubre los dos estándares que exige el parcial: HL7 v2 como entrada de "
        "los legados y FHIR R4 como salida. No trabaja con documentos CDA ni con perfiles IHE (por ejemplo, "
        "PIX/PDQ para identidad de pacientes o ATNA para auditoría); la identidad se resuelve con el número de "
        "documento y la auditoría con la cadena propia. Adoptar IHE sería el paso natural para conectarse con "
        "una red regional.")


def s_val_metodos(w, img):
    w.p("Los modelos UML se validaron en tres niveles, sin herramientas de modelado comerciales:")
    w.vinetas([
        "**Coherencia entre diagramas:** cada archivo de `docs/fase1/diagramas/` tiene una tabla que cruza "
        "actores, participantes, clases y estados (por ejemplo, cada caso de uso con sus participantes en la "
        "secuencia, sus clases y los estados que produce). La revisión fue cruzada entre los dos integrantes.",
        "**Renderizado:** los cuatro diagramas y la arquitectura se escriben en Mermaid y se renderizan a PNG; "
        "un error de sintaxis impide el renderizado.",
        "**Comprobación contra el código:** pruebas automatizadas que comparan el modelo con la "
        "implementación, la comparación de los estados del diagrama con los de `hsb/queue_manager.py` y la "
        "validación FHIR de los Bundles generados.",
    ])
    w.tabla(["Elemento", "Regla de validación", "Herramienta"], [
        ["Casos de uso", "Cada caso de uso tiene un endpoint o función que lo implementa y un participante en la "
         "secuencia", "Tabla de coherencia en `01_casos_uso.md`; revisión cruzada"],
        ["Secuencia", "Cada participante es una clase o un componente desplegado; cada mensaje a `mensaje_bus` "
         "produce un estado del diagrama 4", "Tabla de coherencia en `02_secuencia_hsb.md`"],
        ["Clases", "Cada atributo del dominio corresponde a una columna de `db/schema.sql` y a un campo del "
         "catálogo de 57", "`pytest`: `test_schema_sql_tiene_todas_las_columnas_del_catalogo`"],
        ["Clases (traductor)", "Hay 57 campos numerados y cada uno tiene destino PostgreSQL, MongoDB y FHIR",
         "`pytest`: `test_hay_57_campos_numerados_y_cada_uno_tiene_destino`"],
        ["Estados", "Los 7 estados del diagrama son los valores de `MensajeBus.estado` y los que escribe "
         "`hsb/queue_manager.py`", "Revisión del código; pruebas de reintento, muerto y reencolar"],
        ["Recursos FHIR", "El Bundle generado cumple la especificación FHIR R4", "Operación `$validate` de HAPI "
         "FHIR"],
        ["Sintaxis", "Los diagramas compilan", "Renderizado Mermaid a PNG"],
    ], anchos=[2.6, 7.2, 5.2], titulo="Reglas y herramientas usadas para validar los modelos UML.", tam=8.5)


def s_val_resultados(w, img):
    w.p("El Bundle unificado del paciente 1001 (26 recursos) validó en HAPI con 0 errores, 33 advertencias y "
        "46 mensajes informativos; las advertencias se deben a las extensiones y sistemas de códigos propios. "
        "Las pruebas que comparan el esquema SQL y el catálogo con el modelo pasan (forman parte de las 44). "
        "Los siete estados del diagrama coinciden con los que escribe la cola del bus.")
    w.p("La revisión entre fases encontró inconsistencias entre el modelo y el código, que se corrigieron y se "
        "anotaron en la bitácora: el modelo de datos cubría unos 15 de los 57 campos y suponía el mismo motor "
        "en todas las sedes (se pasó al esquema de 57 campos y a MongoDB en la sede 2); la auditoría del "
        "diagrama era persistente pero el código la guardaba en memoria (se pasó a `pg_central`); el estado "
        "REINTENTANDO terminaba en MUERTO antes de que HAPI volviera (se cambió la política de reintentos); y "
        "la reentrega de un mensaje duplicaba diagnósticos, en contra del principio de idempotencia del "
        "diagrama de secuencia (identificadores deterministas y UPSERT). Los diagramas se actualizaron a la v2.")


def s_val_discusion(w, img):
    w.p("Validar el modelo contra el código con pruebas automáticas fue más útil que una validación solo "
        "visual: la prueba que compara `db/schema.sql` con el catálogo falla en cuanto un campo del modelo no "
        "tiene columna, y así el diagrama de clases no puede quedar desactualizado sin que se note. La "
        "limitación es que la coherencia entre diagramas se revisa a mano con las tablas, sin una herramienta "
        "de validación formal (por ejemplo, reglas OCL), y que el validador FHIR revisa la estructura pero no "
        "la existencia de los códigos CIE-10 y LOINC en sus catálogos oficiales.")


# --------------------------------------------------------------------------------------------
# Evidencias
# --------------------------------------------------------------------------------------------
def _recorte_evidencia(nombre, lineas):
    """Elige el fragmento más útil de cada archivo de evidencia."""
    def desde(marca, n):
        for k, ln in enumerate(lineas):
            if marca in ln:
                return lineas[k:k + n]
        return []
    if nombre.startswith("01_"):
        return lineas[:22] + ["[...]"] + desde("# Pacientes 1007", 1) + [ln for ln in lineas if '"total"' in ln]
    if nombre.startswith("04_"):
        return lineas[:1] + ["[...]"] + desde("$ curl http://localhost:8001/metrics", 22)
    if nombre.startswith("05_"):
        log = desde("# Log del bus", 40)
        log = log[:next((k + 1 for k, ln in enumerate(log) if "tras 7 intentos" in ln), len(log))]
        return (lineas[:4] + ["[...]"] + log + ["[...]"]
                + desde("Reencolar el mensaje", 7) + [ln for ln in lineas if "ENTREGADO tras 1 intentos" in ln])
    if nombre.startswith("06_"):
        return lineas[:2] + ["[... 44 pruebas, todas PASSED ...]"] + lineas[-1:]
    return lineas[:45]


def leer_evidencias():
    if not os.path.isdir(EVIDENCIAS):
        return []
    salida = []
    for f in sorted(os.listdir(EVIDENCIAS)):
        if not f.lower().endswith((".txt", ".log", ".json")):
            continue
        with open(os.path.join(EVIDENCIAS, f), encoding="utf-8", errors="replace") as fh:
            lineas = [ln.rstrip("\n").replace("\t", "    ") for ln in fh]
        while lineas and not lineas[-1].strip():
            lineas.pop()
        corto = [ln if len(ln) <= 118 else ln[:115] + "..." for ln in _recorte_evidencia(f, lineas)]
        salida.append((f, corto))
    return salida


# --------------------------------------------------------------------------------------------
# Ensamblado
# --------------------------------------------------------------------------------------------
def texto_parrafo(el):
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def estilo_de(el):
    ps = el.find(qn("w:pPr") + "/" + qn("w:pStyle"))
    return ps.get(qn("w:val")) if ps is not None else None


def poner_texto(par_el, texto, negrita=None):
    """Reemplaza el texto de un párrafo de la plantilla conservando el formato de su primer run."""
    runs = par_el.findall(qn("w:r"))
    primero = runs[0]
    for r in runs[1:]:
        par_el.remove(r)
    for t in primero.findall(qn("w:t")):
        primero.remove(t)
    for br in primero.findall(qn("w:br")):
        primero.remove(br)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = texto
    primero.append(t)


def construir():
    img_capturas = preparar_imagenes()
    img = dict(img_capturas)
    for f in os.listdir(DIAGRAMAS):
        if f.endswith(".png"):
            img[f[:-4]] = os.path.join(DIAGRAMAS, f)
    evid = leer_evidencias()

    doc = docx.Document(PLANTILLA)
    body = doc.element.body

    # idioma por defecto
    _set_lang(doc.styles["Normal"].element)

    # --- bloque de título -------------------------------------------------------------------
    hijos = list(body.iterchildren())
    poner_texto(hijos[0], TITULO)
    poner_texto(hijos[1], "Autores: Canchila, Jose Guillermo; Manjarrez, Sharit Javier")
    poner_texto(hijos[2], "Sincelejo, Colombia")
    poner_texto(hijos[3], "Correo electrónico: [correo institucional]")

    # --- quitar todo lo que no es título de sección ------------------------------------------
    TITULOS = {"Ttulo1", "Ttulo2", "Ttulo3"}
    for el in hijos[5:]:
        if el.tag == qn("w:sectPr"):
            continue
        if el.tag == qn("w:p") and estilo_de(el) in TITULOS:
            continue
        body.remove(el)

    # --- pie de página con número (antes de crear secciones nuevas, que copian este sectPr) ----
    sec = doc.sections[0]
    pie = sec.footer.paragraphs[0] if sec.footer.paragraphs else sec.footer.add_paragraph()
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _campo(pie, "PAGE", "1")

    w = Escritor(doc)

    # --- tabla de contenido ------------------------------------------------------------------
    w.cursor = hijos[4]
    w.p("**Asignatura:** Sistemas Distribuidos · Parcial final · Noviembre de 2026", alinear="center", despues=2)
    w.p("**Versión:** prototipo v2 (57 campos, traductor universal y sedes con motores distintos)",
        alinear="center", despues=18)
    w.p("**CONTENIDO**", alinear="left", despues=6)
    toc = w._nuevo_parrafo()
    _campo(toc, 'TOC \\o "1-3" \\h \\z \\u', "Actualice la tabla de contenido.")
    w.salto_pagina()

    # --- secciones ---------------------------------------------------------------------------
    secciones = {
        "RESUMEN / ABSTRACT": s_resumen,
        "INTRODUCCIÓN": s_introduccion,
        "OBJETIVOS": s_objetivos,
        "MARCO TEÓRICO": s_marco_teorico,
        "MARCO CONCEPTUAL": s_marco_conceptual,
        "ESTADO DEL ARTE": s_estado_arte,
        "SOLUCIÓN PROPUESTA Y METODOLOGÍA": s_solucion,
        "MODELADO UML": s_uml_intro,
        "Diagrama de Casos de Uso": s_uml_casos,
        "Diagrama de Secuencias": s_uml_secuencia,
        "Diagrama de Clases": s_uml_clases,
        "Diagrama de Estados": s_uml_estados,
        "PROCESO DE DESARROLLO": s_proceso,
        "DISEÑO DE INTERFACES E IMPLEMENTACIÓN": s_interfaces,
        "PROTOTIPO FINAL": s_prototipo,
        "RESULTADOS Y DISCUSIÓN": lambda w_, i_: s_resultados(w_, i_, evid),
        "CONCLUSIONES": s_conclusiones,
        "REFERENCIAS": s_referencias,
        "ANEXOS": lambda w_, i_: s_anexos(w_, i_, evid),
        "AVANCE INICIAL": s_avance_inicial,
        "VIABILIDAD TÉCNICA: ESCALABILIDAD Y CUMPLIMIENTO NORMATIVO": s_viab_intro,
        "Escalabilidad": s_escalabilidad,
        "Cumplimiento normativo": s_cumplimiento,
        "INTEROPERABILIDAD BASADA EN DATOS: ENFOQUE SEMÁNTICO, TÉCNICO Y ORGANIZACIONAL": s_interop_intro,
        "1. Calidad y Gestión de Datos": s_io_calidad,
        "2. Interoperabilidad Semántica": s_io_semantica,
        "3. Interoperabilidad Técnica": s_io_tecnica,
        "4. Gobernanza Organizacional": s_io_gobernanza,
        "5. Herramientas de Integración Técnica": s_io_herr_tecnica,
        "6. Herramientas de Integración Semántica": s_io_herr_semantica,
        "7. Compatibilidad de Herramientas con Estándares de Interoperabilidad": s_io_compat,
        "VALIDACIÓN DE MODELOS UML": lambda w_, i_: None,
        "Métodos": s_val_metodos,
        "Resultados": s_val_resultados,
        "Discusión": s_val_discusion,
    }

    def normal(s):
        return re.sub(r"\s+", " ", s.replace("\u202f", " ").replace("\xa0", " ")).strip()

    claves = {normal(k): v for k, v in secciones.items()}
    encabezados = [el for el in body.iterchildren() if el.tag == qn("w:p") and estilo_de(el) in TITULOS]

    # Dos pasadas: la primera asigna los números de figura para que las referencias del texto que
    # precede a una figura queden con el número correcto; la segunda escribe el documento final.
    def escribir():
        for el in encabezados:
            t = normal(texto_parrafo(el))
            fn = claves.get(t)
            if fn is None:
                print("AVISO: sección sin contenido:", t)
                continue
            w.cursor = el
            fn(w, img)

    import copy as _c
    respaldo = _c.deepcopy(body)
    escribir()
    figs_finales = dict(FIGS)
    # rehacer con los números ya conocidos
    for el in list(body.iterchildren()):
        body.remove(el)
    for el in list(respaldo.iterchildren()):
        body.append(el)
    encabezados[:] = [el for el in body.iterchildren() if el.tag == qn("w:p") and estilo_de(el) in TITULOS]
    FIGS.clear()
    FIGS.update(figs_finales)
    w.n_fig = 0
    w.n_tab = 0
    escribir()

    # toda sección debe referenciar el pie con número
    ref_pie = body.find(qn("w:sectPr")).find(qn("w:footerReference"))
    for sp in body.iter(qn("w:sectPr")):
        if sp.find(qn("w:footerReference")) is None and ref_pie is not None:
            sp.insert(0, _c.deepcopy(ref_pie))

    # --- actualizar campos al abrir ----------------------------------------------------------
    settings = doc.settings.element
    uf = settings.find(qn("w:updateFields"))
    if uf is None:
        uf = OxmlElement("w:updateFields")
        settings.append(uf)
    uf.set(qn("w:val"), "true")

    doc.core_properties.title = TITULO
    doc.core_properties.author = "Canchila, Jose Guillermo; Manjarrez, Sharit Javier"
    doc.core_properties.language = "es-CO"
    doc.save(SALIDA)

    print("Documento:", SALIDA)
    print("Palabras del resumen:", contar_palabras(RESUMEN))
    print("Palabras del título:", contar_palabras(TITULO))
    print("Figuras:", w.n_fig, "· Tablas:", w.n_tab)
    for k, v in sorted(FIGS.items(), key=lambda kv: kv[1]):
        print(f"  Figura {v}: {k}")
    print("Evidencias incluidas:", [n for n, _ in evid] or "ninguna")
    faltan = [f for f in ("19_reporte_incompleto_sede2_caida.png", "20_panel_sede2_caida.png",
                          "21_auditoria_alterada_detectada.png") if f not in img]
    print("Capturas pendientes:", faltan or "ninguna")


if __name__ == "__main__":
    construir()
