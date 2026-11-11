// Genera docs/presentacion/Presentacion_Sustentacion.pptx
// Sustentación del parcial final de Sistemas Distribuidos (15 min + 10 min de preguntas),
// sobre la plantilla institucional de la UNIAJS (fondos en docs/presentacion/plantilla_uniajs/).
//
// Requisitos (no se instalan dentro del proyecto): pptxgenjs, react, react-dom, react-icons, sharp.
//   npm install pptxgenjs react react-dom react-icons sharp      (en una carpeta aparte)
//   NODE_PATH=<esa carpeta>/node_modules node docs/presentacion/construir_presentacion.js
// Opcional: PPTX_APPLY_THEME=<ruta a apply_theme.js de la skill pptx>; si no está, el tema se
// escribe con la función aplicarTema de este archivo.
//
// Las capturas salen de docs/capturas y se recortan en memoria con sharp: el script se puede
// volver a correr sin archivos intermedios.

const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");

const RAIZ = path.resolve(__dirname, "..", "..");
const SALIDA = path.join(__dirname, "Presentacion_Sustentacion.pptx");
const CAPTURAS = path.join(RAIZ, "docs", "capturas");
const PLANTILLA = path.join(__dirname, "plantilla_uniajs");

// ---------------------------------------------------------------- tema (plantilla UNIAJS)
const THEME = {
  name: "UNIAJS Interoperabilidad",
  headFontFace: "Times New Roman",
  bodyFontFace: "Arial",
  colors: {
    dk1: "212529", lt1: "FFFFFF", dk2: "0B2B45", lt2: "F4F7FB",
    accent1: "1B3661", accent2: "C8820A", accent3: "2F6FB0", accent4: "3F8F3A",
    accent5: "1E7E34", accent6: "C82333", hlink: "4376B8", folHlink: "5B6B78",
  },
};
const HEX = THEME.colors;
const AZUL_MEDIO = "4376B8";
const MUTED = "5B6B78";
const LINEA = "D9E1EA";
const TARJETA = "FFFFFF";
const T_AMBAR = "FBF1DE";
const T_AZUL = "E8F0F9";
const T_VERDE = "EAF4E9";
const T_ROJO = "FBE9EB";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Plataforma distribuida de interoperabilidad clínica";
pres.subject = "Sustentación · Sistemas Distribuidos";
pres.author = "Sharith Javier Manjarrez Pacheco · Jose Guillermo Canchila";
pres.company = "Corporación Universitaria Antonio José de Sucre";
const C = pres.SchemeColor;
const NAVY = C.text2;        // 0B2B45: títulos y tarjeta oscura
const BANDA = C.accent1;     // 1B3661: círculos de iconos y flechas
const MONO = "Courier New";
const HEAD = "+mj-lt";

// ---------------------------------------------------------------- utilidades de imagen
async function iconoPng(nombre, color = "FFFFFF", tam = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(fa[nombre], { color: "#" + color, size: tam })
  );
  const buf = await sharp(Buffer.from(svg)).resize(tam, tam).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

// Recorta una captura y le redondea las esquinas. Devuelve {data, w, h}.
async function captura(archivo, x, y, w, h, radio = 16) {
  const buf = await sharp(path.join(CAPTURAS, archivo))
    .extract({ left: x, top: y, width: w, height: h })
    .png()
    .toBuffer();
  const mascara = Buffer.from(
    `<svg width="${w}" height="${h}"><rect x="0" y="0" width="${w}" height="${h}" rx="${radio}" ry="${radio}" fill="#fff"/></svg>`
  );
  const out = await sharp(buf).composite([{ input: mascara, blend: "dest-in" }]).png().toBuffer();
  return { data: "image/png;base64," + out.toString("base64"), w, h };
}

// ---------------------------------------------------------------- utilidades de dibujo
function texto(slide, t, o) {
  slide.addText(t, Object.assign({ isTextBox: true, margin: 0, color: C.text1, fontSize: 14, valign: "top" }, o));
}

function sombra() {
  return { type: "outer", color: "0B2B45", opacity: 0.16, blur: 8, offset: 2, angle: 90 };
}

// Marco redondeado con sombra suave y la captura dentro.
function marco(slide, img, x, y, w, h, nombre) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.1, fill: { color: C.background1 },
    line: { color: LINEA, width: 0.75 }, shadow: sombra(), objectName: nombre + " marco",
  });
  const p = 0.07;
  const bw = w - 2 * p, bh = h - 2 * p;
  const r = img.w / img.h;
  let iw = bw, ih = bw / r;
  if (ih > bh) { ih = bh; iw = bh * r; }
  slide.addImage({
    data: img.data, x: x + p + (bw - iw) / 2, y: y + p + (bh - ih) / 2, w: iw, h: ih,
    altText: nombre, objectName: nombre,
  });
}

function altoMarco(img, w) { return (w - 0.14) * img.h / img.w + 0.14; }

function circuloIcono(slide, icono, x, y, d, fill, nombre) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill || BANDA }, line: { type: "none" }, objectName: nombre + " círculo" });
  const k = d * 0.52;
  slide.addImage({ data: icono, x: x + (d - k) / 2, y: y + (d - k) / 2, w: k, h: k, altText: nombre, objectName: nombre + " icono" });
}

function flecha(slide, x1, y1, x2, y2, color, nombre, ancho = 1.75) {
  slide.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipH: x2 < x1, flipV: y2 < y1,
    line: { color: color || BANDA, width: ancho, endArrowType: "triangle" }, objectName: nombre,
  });
}

function caja(slide, x, y, w, h, fill, linea, nombre, radio = 0.08) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: radio, fill: { color: fill },
    line: linea ? { color: linea, width: 1 } : { type: "none" }, objectName: nombre,
  });
}

// Tarjeta blanca con borde claro (estilo de la plantilla).
function tarjeta(slide, x, y, w, h, nombre) {
  caja(slide, x, y, w, h, TARJETA, LINEA, nombre, 0.1);
}

function pastilla(slide, t, x, y, w, h, fill, color, o = {}) {
  slide.addText(t, Object.assign({
    shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: h / 2, x, y, w, h, fill: { color: fill },
    color, fontSize: 13, bold: true, align: "center", valign: "middle", margin: 0, objectName: "pastilla " + (typeof t === "string" ? t : ""),
  }, o));
}

// ---------------------------------------------------------------- layouts (fondos de la plantilla)
function definirLayouts() {
  pres.defineSlideMaster({
    title: "PORTADA",
    background: { path: path.join(PLANTILLA, "fondo_portada.jpg") },
    objects: [],
  });
  pres.defineSlideMaster({
    title: "CONTENIDO",
    background: { path: path.join(PLANTILLA, "fondo_contenido.jpg") },
    margin: [1.15, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 2.95, y: 0.55, w: 9.8, h: 0.75, fontFace: HEAD, fontSize: 30, bold: false, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
    ],
    slideNumber: { x: 12.33, y: 6.9, w: 0.4, h: 0.22, fontSize: 10, color: MUTED, align: "right", margin: 0 },
  });
  pres.defineSlideMaster({
    title: "CIERRE",
    background: { path: path.join(PLANTILLA, "fondo_cierre.jpg") },
    objects: [],
  });
}

// ---------------------------------------------------------------- diapositivas
async function construir() {
  definirLayouts();

  const I = {};
  for (const n of ["FaDatabase", "FaLeaf", "FaExchangeAlt", "FaShieldAlt", "FaKey", "FaLink", "FaRedo", "FaCheckCircle",
    "FaFileMedical", "FaUsers", "FaClipboardList", "FaBan", "FaUserPlus", "FaLayerGroup", "FaFingerprint", "FaInbox",
    "FaTachometerAlt", "FaCubes", "FaIdCard", "FaUserCog", "FaStethoscope", "FaFileAlt", "FaPuzzlePiece",
    "FaBalanceScale", "FaUndo", "FaClone", "FaVial", "FaPowerOff", "FaRandom"]) {
    I[n] = await iconoPng(n);
  }
  const IA = { FaExclamationTriangle: await iconoPng("FaExclamationTriangle", HEX.accent2) };

  // capturas recortadas (coordenadas en píxeles de las originales de 1440 px)
  const S = {
    resumen: await captura("02_panel_resumen.png", 320, 300, 1020, 810),
    usuarios: await captura("04_panel_usuarios.png", 330, 230, 1010, 640),
    denegado: await captura("17_acceso_denegado_403.png", 430, 230, 580, 440),
    cuenta: await captura("09_admision_paciente_y_cuenta.png", 100, 200, 1240, 450),
    paciente: await captura("11_portal_paciente.png", 0, 0, 1440, 615),
    admision: await captura("08_admision_busqueda_1001.png", 0, 0, 1440, 615),
    medico: await captura("13_medico_registro_con_codigo.png", 0, 0, 1440, 615),
    reporte: await captura("14_reporte_hc_1001.png", 0, 0, 1440, 615),
    incompleto: await captura("19_reporte_incompleto_sede2_caida.png", 130, 460, 1180, 330),
    sedeCaida: await captura("20_panel_sede2_caida.png", 340, 800, 1010, 365),
  };

  // Las diapositivas de contenido se diseñaron sobre la zona y 1.35–6.8 in. El logo del fondo de la
  // plantilla llega hasta y ≈ 1.45 in, así que todo el contenido se lleva a la zona y 1.65–6.83 in con
  // una escala uniforme (k = 0,95) centrada en el ancho de la diapositiva. Los tamaños de letra no cambian.
  const K = 0.95, CX = 13.333 / 2;
  const ajustar = (o) => {
    if (!o || o.placeholder) return o;
    if (typeof o.x === "number") o.x = CX + (o.x - CX) * K;
    if (typeof o.y === "number") o.y = 1.65 + (o.y - 1.35) * K;
    if (typeof o.w === "number") o.w *= K;
    if (typeof o.h === "number") o.h *= K;
    return o;
  };
  const contenido = (seccion, titulo, subtitulo) => {
    const s = pres.addSlide({ masterName: "CONTENIDO", sectionTitle: seccion });
    s.addText(titulo, { placeholder: "title" });
    if (subtitulo) texto(s, subtitulo, { x: 0.6, y: 1.58, w: 11.5, h: 0.3, fontSize: 13, italic: true, color: MUTED });
    return {
      addText: (t, o) => s.addText(t, ajustar(o)),
      addShape: (tipo, o) => s.addShape(tipo, ajustar(o)),
      addImage: (o) => s.addImage(ajustar(o)),
      addChart: (tipo, d, o) => s.addChart(tipo, d, ajustar(o)),
      addNotes: (n) => s.addNotes(n),
    };
  };

  // ============================================================ 1. Portada
  pres.addSection({ title: "Apertura" });
  {
    const s = pres.addSlide({ masterName: "PORTADA", sectionTitle: "Apertura" });
    const p = (t, o) => ({ text: t, options: Object.assign({ breakLine: true, fontFace: HEAD, color: C.text1 }, o) });
    texto(s, [
      p("Plataforma distribuida de interoperabilidad clínica", { fontSize: 28, bold: true, color: NAVY, paraSpaceAfter: 2 }),
      p("Red de IPS Sincelejo · Cartagena · Corozal", { fontSize: 18, italic: true, color: NAVY, paraSpaceAfter: 14 }),
      p("Autores", { fontSize: 14, bold: true, color: AZUL_MEDIO, paraSpaceAfter: 2 }),
      p("Sharith Javier Manjarrez Pacheco", { fontSize: 16 }),
      p("Jose Guillermo Canchila", { fontSize: 16, paraSpaceAfter: 12 }),
      p("Corporación Universitaria Antonio José de Sucre", { fontSize: 14 }),
      p("Facultad de Ciencias de la Ingeniería · Sistemas Distribuidos — Parcial final", { fontSize: 14, paraSpaceAfter: 10 }),
      p("Docente: [nombre del docente]", { fontSize: 14, bold: true, paraSpaceAfter: 2 }),
      { text: "Sincelejo, Sucre · 2026", options: { fontFace: HEAD, fontSize: 13, color: MUTED } },
    ], { x: 1.67, y: 2.6, w: 10.0, h: 4.05, align: "center", valign: "top" });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "Buenos días. Somos Jose Guillermo Canchila y Sharith Javier Manjarrez y vamos a sustentar la plataforma distribuida de interoperabilidad clínica para la red de IPS de Sincelejo, Cartagena y Corozal. " +
      "En 15 minutos vamos a alternar diapositivas cortas con la demostración en vivo, en el orden de la guía de la Fase 5: arranque limpio, cobertura en 0 %, mensajes HL7 y CSV, duplicado, caída de una sede, auditoría alterada y consulta unificada. " +
      "Mientras hablo, B deja corriendo el arranque limpio (docker compose down -v && docker compose up -d --build), porque el servidor FHIR tarda unos 90 segundos en responder."
    );
  }

  // ============================================================ 2. El problema
  {
    const s = contenido("Apertura", "Una historia clínica partida en tres sedes");
    const sedes = [
      ["Sede 1 · Sincelejo", "PostgreSQL", "HL7 · laboratorio", C.accent3, T_AZUL, "FaDatabase"],
      ["Sede 2 · Cartagena", "MongoDB", "HL7 · admisión", C.accent4, T_VERDE, "FaLeaf"],
      ["Sede 3 · Corozal", "PostgreSQL", "Archivo CSV", C.accent3, T_AZUL, "FaDatabase"],
    ];
    sedes.forEach(([nom, motor, fmt, col, tinte, ic], i) => {
      const y = 1.45 + i * 1.75;
      tarjeta(s, 0.6, y, 5.3, 1.4, "tarjeta " + nom);
      circuloIcono(s, I[ic], 0.85, y + 0.3, 0.8, col, nom);
      texto(s, nom, { x: 1.9, y: y + 0.2, w: 3.85, h: 0.42, fontSize: 19, bold: true, color: NAVY, valign: "middle" });
      pastilla(s, motor, 1.9, y + 0.78, 1.45, 0.38, tinte, col, { fontSize: 12 });
      texto(s, fmt, { x: 3.5, y: y + 0.78, w: 2.3, h: 0.38, fontSize: 14, color: MUTED, valign: "middle" });
      flecha(s, 5.9, y + 0.7, 7.15, 3.85, BANDA, "flecha " + nom, 2);
    });
    caja(s, 7.3, 1.75, 5.43, 4.2, NAVY, null, "meta", 0.12);
    circuloIcono(s, I.FaFileMedical, 7.65, 2.1, 0.95, AZUL_MEDIO, "historia unificada");
    texto(s, "Una sola historia, sin reemplazar los legados", { x: 8.8, y: 2.1, w: 3.75, h: 0.95, fontFace: HEAD, fontSize: 22, bold: true, color: C.background1, valign: "middle" });
    const metas = [
      ["FaClipboardList", "57 campos de la Res. 866 de 2021"],
      ["FaExchangeAlt", "Publicada en el estándar FHIR R4"],
      ["FaShieldAlt", "Cada acceso queda auditado"],
    ];
    metas.forEach(([ic, t], i) => {
      const y = 3.45 + i * 0.75;
      circuloIcono(s, I[ic], 7.75, y, 0.5, AZUL_MEDIO, t);
      texto(s, t, { x: 8.45, y, w: 4.15, h: 0.5, fontSize: 16, valign: "middle", color: C.background1 });
    });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "El problema: la red tiene tres sedes y cada una conserva su sistema legado, con su propia base y su propio motor. Sincelejo y Corozal usan PostgreSQL; Cartagena, MongoDB. " +
      "Además envían en formatos distintos: Sincelejo manda resultados de laboratorio en HL7 (mensaje ORU^R01), Cartagena manda admisiones en HL7 (ADT^A01) y Corozal exporta un CSV separado por punto y coma. " +
      "El resultado es que la historia de un mismo paciente queda partida en tres. " +
      "La meta fue unificarla con los 57 campos de la Resolución 866 de 2021 y publicarla en FHIR R4, sin pedirle a ninguna sede que cambie su sistema."
    );
  }

  // ============================================================ 3. Arquitectura
  pres.addSection({ title: "Arquitectura" });
  {
    const s = contenido("Arquitectura", "Siete contenedores, un solo comando");
    texto(s, "Sistemas legados", { x: 0.6, y: 1.4, w: 2.3, h: 0.3, fontSize: 12, bold: true, color: MUTED });
    const leg = [["Sincelejo · HL7", C.accent3], ["Cartagena · HL7", C.accent4], ["Corozal · CSV", C.accent3]];
    leg.forEach(([t, col], i) => {
      const y = 1.85 + i * 0.85;
      pastilla(s, t, 0.6, y, 2.2, 0.6, C.background1, col, { line: { color: col, width: 1.25 }, fontSize: 13 });
      flecha(s, 2.8, y + 0.3, 3.4, 3.2, MUTED, "entrada " + t, 1.25);
    });
    // Bus de integración (la tarjeta oscura de la diapositiva)
    s.addText([
      { text: "Bus de integración", options: { bold: true, fontSize: 17, breakLine: true } },
      { text: "traduce 57 campos · valida · evita duplicados · reintenta", options: { fontSize: 12 } },
    ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, x: 3.4, y: 2.45, w: 3.0, h: 1.5, fill: { color: NAVY }, color: C.background1, align: "center", valign: "middle", margin: 6, objectName: "Bus de integración" });
    // Servidor FHIR
    s.addText([
      { text: "Servidor FHIR", options: { bold: true, fontSize: 17, breakLine: true, color: NAVY } },
      { text: "publica cada paquete FHIR R4", options: { fontSize: 12, color: C.text1 } },
    ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, x: 7.15, y: 2.45, w: 2.75, h: 1.5, fill: { color: C.background1 }, line: { color: AZUL_MEDIO, width: 1.5 }, align: "center", valign: "middle", margin: 6, objectName: "Servidor FHIR" });
    flecha(s, 6.4, 3.2, 7.15, 3.2, NAVY, "bus a servidor FHIR", 2);
    texto(s, "1º publica en FHIR", { x: 5.85, y: 1.98, w: 1.9, h: 0.3, fontSize: 12, bold: true, color: NAVY, align: "center" });
    flecha(s, 6.8, 2.28, 6.8, 3.15, NAVY, "guía 1º", 0.75);
    // Bases de las sedes
    const sedes = [["Base de Sincelejo", "(PostgreSQL)", C.accent3, T_AZUL, 2.7], ["Base de Cartagena", "(MongoDB)", C.accent4, T_VERDE, 4.98], ["Base de Corozal", "(PostgreSQL)", C.accent3, T_AZUL, 7.26]];
    sedes.forEach(([n, d, col, tinte, x]) => {
      s.addText([
        { text: n, options: { bold: true, fontSize: 14, breakLine: true, color: col } },
        { text: d, options: { fontSize: 12, color: C.text1 } },
      ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, x, y: 5.2, w: 2.15, h: 1.0, fill: { color: tinte }, line: { color: col, width: 1.25 }, align: "center", valign: "middle", margin: 4, objectName: n });
      flecha(s, 4.9, 3.95, x + 1.075, 5.2, NAVY, "bus a " + n, 1.5);
    });
    texto(s, "2º guarda en la sede\nsin duplicar", { x: 0.6, y: 4.3, w: 3.0, h: 0.5, fontSize: 12, bold: true, color: NAVY, align: "right" });
    // Portal web y API
    pastilla(s, "4 vistas por rol", 10.3, 1.35, 2.43, 0.55, C.background1, C.text1, { line: { color: MUTED, width: 1 }, fontSize: 13 });
    flecha(s, 11.515, 1.9, 11.515, 2.45, MUTED, "vistas a portal", 1.5);
    s.addText([
      { text: "Portal web y API", options: { bold: true, fontSize: 16, breakLine: true, color: NAVY } },
      { text: "token de sesión (JWT) · roles · consulta en paralelo", options: { fontSize: 12, color: C.text1 } },
    ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, x: 10.3, y: 2.45, w: 2.43, h: 1.5, fill: { color: C.background2 }, line: { color: AZUL_MEDIO, width: 1.5 }, align: "center", valign: "middle", margin: 6, objectName: "Portal web y API" });
    s.addText([
      { text: "Base central", options: { bold: true, fontSize: 14, breakLine: true, color: C.accent2 } },
      { text: "(auditoría y cuentas)", options: { fontSize: 12, color: C.text1 } },
    ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, x: 10.3, y: 5.2, w: 2.43, h: 1.0, fill: { color: T_AMBAR }, line: { color: C.accent2, width: 1.25 }, align: "center", valign: "middle", margin: 4, objectName: "Base central" });
    flecha(s, 11.515, 3.95, 11.515, 5.2, C.accent2, "portal a base central", 1.5);
    flecha(s, 10.3, 3.8, 9.41, 5.2, AZUL_MEDIO, "portal a sedes", 1.5);
    texto(s, "lee las 3 sedes en paralelo", { x: 6.95, y: 4.35, w: 2.6, h: 0.3, fontSize: 12, bold: true, color: AZUL_MEDIO, align: "right" });
    // un solo comando
    circuloIcono(s, I.FaCubes, 0.6, 6.33, 0.45, BANDA, "contenedores");
    texto(s, "Se levanta con un solo comando, desde cero", { x: 1.2, y: 6.33, w: 7.5, h: 0.45, fontSize: 16, bold: true, color: NAVY, valign: "middle" });
    s.addNotes(
      "Presenta A (Jose), mientras el servidor FHIR termina de arrancar (bloque 1 del guion).\n" +
      "Son siete contenedores que suben con un solo comando desde volúmenes vacíos: docker compose down -v && docker compose up -d --build. " +
      "Las tres bases de las sedes, cada una con su motor: Sincelejo (contenedor pg_sede1), Cartagena (mongo_sede2) y Corozal (pg_sede3). " +
      "El bus de integración (contenedor hsb_bus, puerto 8001) recibe HL7, CSV y JSON, traduce al registro de 57 campos, valida, evita duplicados y reintenta. Primero publica en el servidor FHIR (contenedor hapi_fhir_r4, puerto 8090) y después guarda en la sede. " +
      "El portal web y API (contenedor api_gateway, puerto 8000) valida el token de sesión y los permisos y sirve las cuatro vistas; la consulta unificada pregunta a las tres sedes en paralelo. La base central (contenedor pg_central) guarda la auditoría encadenada y las cuentas. " +
      "Regla de oro: ninguna vista habla con las bases; lecturas por la API, escrituras por el bus.\n\n" +
      "Pregunta probable: ¿qué escalaría primero con 100 veces más mensajes? Respuesta: el bus. Pondríamos un broker (Kafka o RabbitMQ, una partición por sede) y varias réplicas del bus; ya son casi sin estado porque el registro de mensajes vive en cada sede. Después varios servidores FHIR y al final réplicas de lectura en las sedes."
    );
  }

  // ============================================================ 4. Motores distintos
  {
    const s = contenido("Arquitectura", "Por qué cada sede tiene su propio motor");
    const cols = [
      ["Sede 1 · Sincelejo", "PostgreSQL", C.accent3, T_AZUL, "FaDatabase", "tabla", "Usuario, atención, diagnósticos y egreso en una transacción ACID"],
      ["Sede 2 · Cartagena", "MongoDB", C.accent4, T_VERDE, "FaLeaf", "doc", "Un documento por paciente: la atención se escribe de forma atómica"],
      ["Sede 3 · Corozal", "PostgreSQL", C.accent3, T_AZUL, "FaDatabase", "tabla", "Mismo esquema relacional, otro nodo, otros datos"],
    ];
    cols.forEach(([nom, motor, col, tinte, ic, tipo, desc], i) => {
      const x = 0.6 + i * 4.13;
      caja(s, x, 1.4, 3.87, 3.3, tinte, LINEA, "tarjeta " + nom, 0.1);
      circuloIcono(s, I[ic], x + 0.25, 1.65, 0.7, col, motor);
      texto(s, nom, { x: x + 1.1, y: 1.62, w: 2.7, h: 0.38, fontSize: 16, bold: true, color: NAVY, valign: "middle" });
      texto(s, motor, { x: x + 1.1, y: 2.0, w: 2.7, h: 0.36, fontSize: 15, bold: true, color: col, valign: "middle" });
      if (tipo === "tabla") {
        for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) {
          s.addShape(pres.shapes.RECTANGLE, { x: x + 0.3 + c * 0.82, y: 2.65 + r * 0.3, w: 0.8, h: 0.28, fill: { color: r === 0 ? col : C.background1 }, line: { color: col, width: 0.5 }, objectName: "celda" });
        }
      } else {
        texto(s, '{ paciente: "1007",\n  datos: {…},\n  atenciones: [ {…} ] }', { x: x + 0.3, y: 2.6, w: 3.3, h: 0.95, fontFace: MONO, fontSize: 12, color: C.text1, fill: { color: C.background1 }, margin: 6 });
      }
      texto(s, desc, { x: x + 0.3, y: 3.7, w: 3.3, h: 0.9, fontSize: 14, color: C.text1 });
    });
    const ideas = [
      ["FaPuzzlePiece", "Persistencia políglota", "Un repositorio con una sola interfaz para los dos motores"],
      ["FaUndo", "ACID dentro de cada sede", "Sin transacción distribuida: cada nodo es atómico por sí solo"],
      ["FaBalanceScale", "CAP: AP en las lecturas", "Si una sede cae, se responde con las otras y se avisa"],
    ];
    ideas.forEach(([ic, h, d], i) => {
      const x = 0.6 + i * 4.13;
      circuloIcono(s, I[ic], x, 5.05, 0.62, BANDA, h);
      texto(s, h, { x: x + 0.8, y: 4.97, w: 3.1, h: 0.4, fontSize: 15, bold: true, color: NAVY, valign: "middle" });
      texto(s, d, { x: x + 0.8, y: 5.38, w: 3.1, h: 0.95, fontSize: 14, color: MUTED });
    });
    s.addNotes(
      "Presenta B (Sharith).\n" +
      "El escenario dice que cada sede conserva su sistema, y el docente pidió que no todas usaran el mismo motor. Elegimos MongoDB para Cartagena porque es el caso más distinto de un relacional: un documento por paciente, con las atenciones dentro y otros nombres de campo. " +
      "Si la plataforma funciona con eso, no depende de un esquema único. Para el bus y la consulta los dos motores se ven igual: un repositorio con la misma interfaz (RepositorioPostgres y RepositorioMongo). " +
      "La atomicidad es local: en PostgreSQL, una transacción; en MongoDB, una escritura de un documento (replace_one). No usamos transacción distribuida (2PC). " +
      "En las lecturas elegimos disponibilidad: si una sede no responde, se devuelve lo de las otras con el reporte marcado como incompleto.\n\n" +
      "Pregunta probable: si la sede 2 cae a mitad de una transacción, ¿qué garantiza y qué sacrifica? Respuesta: dentro de la sede, o queda el documento nuevo o el anterior, nunca media atención. Entre el servidor FHIR y la sede hay consistencia eventual con reintentos que no duplican. Se sacrifica consistencia mientras dura la partición: el médico no ve Cartagena, pero el sistema le avisa."
    );
  }

  // ============================================================ 5. Traductor 57 campos
  {
    const s = contenido("Arquitectura", "Un traductor universal de 57 campos", "Viaje del campo 14 · municipio de residencia (código DANE)");
    const nodo = (x, y, w, h, et, val, col, tinte, nombre, mono = true) => {
      caja(s, x, y, w, h, tinte, col, nombre, 0.08);
      texto(s, et, { x: x + 0.15, y: y + 0.12, w: w - 0.3, h: 0.3, fontSize: 13, bold: true, color: col });
      texto(s, val, { x: x + 0.15, y: y + 0.45, w: w - 0.3, h: h - 0.55, fontFace: mono ? MONO : undefined, fontSize: mono ? 11 : 12, color: C.text1 });
    };
    nodo(0.6, 1.95, 2.6, 1.55, "HL7 v2.5", "Segmento del paciente, campo 11.9 (PID-11.9) = \"70001\"", NAVY, C.background1, "nodo HL7", false);
    nodo(3.6, 2.1, 2.6, 1.25, "Catálogo · fila 14", "Registro común (canónico) de 57 campos", BANDA, C.background2, "nodo catálogo", false);
    nodo(6.6, 1.7, 3.15, 1.0, "PostgreSQL · sedes 1 y 3", "usuario.municipio_residencia", C.accent3, T_AZUL, "nodo postgres");
    nodo(6.6, 2.85, 3.15, 1.0, "MongoDB · sede 2", "residencia.municipio_dane", C.accent4, T_VERDE, "nodo mongo");
    nodo(10.15, 2.1, 2.58, 1.25, "FHIR R4", "Patient.address\n.district", BANDA, C.background2, "nodo fhir");
    flecha(s, 3.2, 2.72, 3.6, 2.72, NAVY, "f1", 2);
    flecha(s, 6.2, 2.72, 6.6, 2.2, NAVY, "f2", 2);
    flecha(s, 6.2, 2.72, 6.6, 3.35, NAVY, "f3", 2);
    flecha(s, 9.75, 2.72, 10.15, 2.72, NAVY, "f4", 2);
    const stats = [
      ["57", "campos en un catálogo", "cada uno con su origen (HL7 o CSV) y su destino en PostgreSQL, MongoDB y FHIR"],
      ["4", "segmentos Z", "ZPI · ZPV · ZRX · ZEG: campos extra que HL7 v2.5 no trae"],
      ["56/57", "campos del mensaje completo", "100 % de los obligatorios; solo falta el 42 (el paciente sale vivo)"],
    ];
    stats.forEach(([n, l, d], i) => {
      const x = 0.6 + i * 4.13;
      tarjeta(s, x, 4.3, 3.87, 2.45, "dato " + l);
      texto(s, n, { x: x + 0.3, y: 4.45, w: 3.3, h: 0.85, fontFace: HEAD, fontSize: 44, bold: true, color: NAVY, valign: "middle" });
      texto(s, l, { x: x + 0.3, y: 5.32, w: 3.3, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
      texto(s, d, { x: x + 0.3, y: 5.72, w: 3.3, h: 0.95, fontSize: 13, color: MUTED });
    });
    s.addNotes(
      "Presenta B (Sharith).\n" +
      "El corazón del bus es un catálogo único de 57 campos (traductor/catalogo_57.py): para cada campo dice de dónde sale en HL7 o CSV, en qué columna queda en PostgreSQL, en qué ruta en MongoDB y en qué elemento de FHIR. " +
      "Ejemplo, campo 14, municipio de residencia: llega en el segmento del paciente de HL7, campo 11, componente 9 (PID-11.9), con el código DANE 70001; el traductor llena el registro común; en Cartagena queda en residencia.municipio_dane, en las sedes PostgreSQL en usuario.municipio_residencia, y en FHIR en la dirección del paciente, elemento district. " +
      "Lo que HL7 v2.5 no trae viaja en cuatro segmentos Z que acordamos para el proyecto. Con el mensaje completo cubrimos 56 de 57 campos; solo falta el 42, diagnóstico de muerte, porque el paciente sale vivo.\n\n" +
      "Pregunta probable: ¿cómo maneja el traductor esquemas distintos? Respuesta: ninguna función tiene nombres de columna escritos a mano; a_postgres, a_mongo y sus inversas los toman del catálogo. Hay una prueba de ida y vuelta registro común → MongoDB → registro común que conserva los 57."
    );
  }

  // ============================================================ 6. Bus y estados
  {
    const s = contenido("Arquitectura", "El bus: cada mensaje tiene un estado");
    const est = (t, x, y, fill, color, w = 1.9) => pastilla(s, t, x, y, w, 0.58, fill, color, { fontSize: 12, line: { color: color === C.background1 ? fill : color, width: 1.25 } });
    est("RECIBIDO", 0.6, 1.6, C.background2, NAVY);
    est("VALIDADO", 2.85, 1.6, C.background2, NAVY);
    est("TRANSFORMADO", 5.1, 1.6, C.background2, NAVY);
    est("ENTREGADO", 7.35, 1.6, C.accent5, C.background1);
    flecha(s, 2.5, 1.89, 2.85, 1.89, NAVY, "e1"); flecha(s, 4.75, 1.89, 5.1, 1.89, NAVY, "e2"); flecha(s, 7.0, 1.89, 7.35, 1.89, NAVY, "e3");
    est("RECHAZADO", 1.95, 3.2, T_ROJO, C.accent6);
    flecha(s, 2.25, 2.18, 2.25, 3.2, C.accent6, "r1", 1.25); flecha(s, 3.55, 2.18, 3.55, 3.2, C.accent6, "r2", 1.25);
    est("DUPLICADO", 0.6, 4.6, C.background1, MUTED, 1.5);
    flecha(s, 0.9, 2.18, 0.9, 4.6, MUTED, "d1", 1.25);
    est("REINTENTANDO", 5.1, 3.2, T_AMBAR, C.accent2);
    flecha(s, 6.05, 2.18, 6.05, 3.2, C.accent2, "t1", 1.25);
    flecha(s, 7.0, 3.35, 7.9, 2.18, C.accent5, "t2", 1.25);
    texto(s, "reintento OK", { x: 7.65, y: 2.7, w: 1.4, h: 0.3, fontSize: 12, color: C.accent5, bold: true });
    est("MUERTO", 5.1, 4.6, C.accent6, C.background1);
    flecha(s, 5.6, 3.78, 5.6, 4.6, C.accent6, "m1", 1.25);
    flecha(s, 6.5, 4.6, 6.5, 3.78, C.accent2, "m2", 1.25);
    texto(s, "7 intentos\no error de datos", { x: 3.55, y: 3.85, w: 1.95, h: 0.6, fontSize: 12, color: C.accent6, align: "right" });
    texto(s, "reencolar (manual)", { x: 6.62, y: 4.0, w: 2.2, h: 0.3, fontSize: 12, color: C.accent2, bold: true });
    texto(s, "Esperas entre intentos (segundos), en segundo plano: la respuesta ya se envió", { x: 0.6, y: 5.5, w: 8.6, h: 0.3, fontSize: 13, color: MUTED });
    [2, 4, 8, 16, 32, 64].forEach((n, i) => {
      s.addText(String(n), { shape: pres.shapes.OVAL, x: 0.6 + i * 0.85, y: 5.9, w: 0.62, h: 0.62, fill: { color: C.accent2 }, color: C.background1, bold: true, fontSize: 15, align: "center", valign: "middle", margin: 0, objectName: "espera " + n });
    });
    texto(s, "= 7 intentos", { x: 5.75, y: 5.9, w: 2, h: 0.62, fontSize: 16, bold: true, color: C.accent2, valign: "middle" });
    const n = [
      ["FaFingerprint", "No se duplica", "El número del mensaje o su huella SHA-256 queda en el registro de mensajes de la sede"],
      ["FaRandom", "Primero FHIR, luego la sede", "Repetir los dos pasos es seguro: se guarda sin duplicar"],
      ["FaBan", "Error de datos: MUERTO", "Si el dato viola una regla, reintentar no lo arregla"],
    ];
    n.forEach(([ic, h, d], i) => {
      const y = 1.45 + i * 1.8;
      circuloIcono(s, I[ic], 9.55, y, 0.62, BANDA, h);
      texto(s, h, { x: 10.35, y: y - 0.05, w: 2.4, h: 0.65, fontSize: 15, bold: true, color: NAVY, valign: "middle" });
      texto(s, d, { x: 10.35, y: y + 0.65, w: 2.4, h: 1.05, fontSize: 13, color: MUTED });
    });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "Cada mensaje recorre estados que quedan guardados en el registro de mensajes de su sede (tabla mensaje_bus): recibido, validado, transformado y entregado. Lo que no cumple las reglas se rechaza con todos sus motivos. " +
      "Antes de validar, el bus busca el número del mensaje (campo MSH-10 de HL7) o la huella SHA-256 del contenido: si ya lo entregó, responde duplicado sin tocar nada. " +
      "Primero publica en el servidor FHIR y luego guarda en la sede. Si alguno no responde, el mensaje pasa a reintentando: la petición ya respondió 202 y un hilo en segundo plano reintenta con esperas de 2 a 64 segundos, 7 intentos. Si se agotan queda muerto, y se puede reencolar con POST /hsb/reencolar/{id}. " +
      "Los errores de datos (un 4xx del servidor FHIR o una restricción violada en la sede) van directo a muerto, porque el mismo dato fallará igual en el intento 7.\n\n" +
      "Pregunta probable: ¿qué pasa si el bus muere entre «FHIR OK» y «sede OK»? Respuesta: el mensaje quedó en TRANSFORMADO con su contenido original. Al arrancar, recuperar_pendientes() lo relee de las sedes y lo reprograma; FHIR reemplaza el mismo recurso y la sede guarda sin duplicar (UPSERT), así que termina ENTREGADO. Lo medimos: recuperó 2 mensajes pendientes."
    );
  }

  // ============================================================ 7. FHIR R4
  {
    const s = contenido("Arquitectura", "FHIR R4: un paquete por mensaje, sin duplicados");
    const tipos = ["Condition", "Observation", "Organization", "Practitioner", "Encounter", "MedicationRequest", "Patient", "AllergyIntolerance"];
    const vals = [7, 5, 3, 3, 3, 3, 1, 1];
    tarjeta(s, 0.6, 1.35, 6.5, 5.45, "tarjeta gráfico");
    s.addChart(pres.charts.BAR, [{ name: "Recursos", labels: tipos.slice().reverse(), values: vals.slice().reverse() }], {
      x: 0.75, y: 1.45, w: 6.2, h: 5.25, barDir: "bar", chartColors: [HEX.accent1],
      showTitle: true, title: "Paquete FHIR del paciente 1001 · 26 recursos", titleFontSize: 15, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
      catAxisLabelColor: MUTED, catAxisLabelFontSize: 12, catAxisLabelFontFace: "+mn-lt",
      valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
      catAxisLineShow: false, showLegend: false, barGapWidthPct: 45,
    });
    tarjeta(s, 7.4, 1.35, 5.33, 2.2, "cero errores");
    circuloIcono(s, I.FaCheckCircle, 7.7, 1.7, 0.8, C.accent5, "validado");
    texto(s, "0 errores", { x: 8.75, y: 1.55, w: 3.8, h: 0.9, fontFace: HEAD, fontSize: 44, bold: true, color: C.accent5, valign: "middle" });
    texto(s, "en la validación oficial FHIR del servidor (33 advertencias por extensiones propias)", { x: 8.75, y: 2.45, w: 3.85, h: 0.95, fontSize: 13, color: C.text1 });
    caja(s, 7.4, 3.8, 5.33, 1.75, NAVY, null, "nombres fijos", 0.1);
    texto(s, [
      { text: "Cada recurso tiene un nombre fijo", options: { bold: true, breakLine: true, fontSize: 15 } },
      { text: "Paciente 1007 → Patient/pac-1007", options: { breakLine: true } },
      { text: "Atención V-S2-0101 → Encounter/enc-V-S2-0101" },
    ], { x: 7.65, y: 3.98, w: 4.95, h: 1.4, fontSize: 13, color: C.background1, paraSpaceAfter: 6 });
    circuloIcono(s, I.FaFingerprint, 7.4, 5.9, 0.55, BANDA, "sin duplicar");
    texto(s, "Reenviar el mensaje reemplaza el mismo recurso: no se duplica", { x: 8.1, y: 5.83, w: 4.63, h: 0.7, fontSize: 14, color: C.text1, valign: "middle" });
    s.addNotes(
      "Presenta B (Sharith).\n" +
      "Cada mensaje se convierte en un paquete FHIR (un Bundle de tipo transaction). Todas sus entradas usan PUT con nombres fijos: Patient/pac más el documento, Encounter/enc más el número de visita, y así. " +
      "Por eso reenviar el mismo mensaje no crea otro paciente: reemplaza el mismo recurso. " +
      "La historia del paciente 1001, armada con atenciones de las tres sedes, da un paquete de 26 recursos; lo pasamos por la validación oficial del servidor FHIR (operación $validate de HAPI) y salió con 0 errores. Las 33 advertencias vienen de extensiones y sistemas de códigos propios que el servidor no puede resolver.\n\n" +
      "Pregunta probable: ¿por qué reenviar un mensaje no crea un paciente duplicado? Respuesta: tres capas, y cualquiera sola basta: el bus reconoce el número del mensaje (MSH-10) o la huella en el registro de mensajes de la sede; el paquete FHIR usa PUT a nombres fijos; y la sede guarda por la misma llave (ON CONFLICT en PostgreSQL, _id en MongoDB). Medido: 1 solo Patient 1007 y 1 documento en MongoDB tras el reenvío."
    );
  }

  // ============================================================ 8. Seguridad
  pres.addSection({ title: "Seguridad y vistas" });
  {
    const s = contenido("Seguridad y vistas", "Seguridad: permisos en la API, auditoría encadenada");
    const filas = [
      ["FaKey", "Token de sesión (JWT)", "La API valida el token y el rol, no la pantalla"],
      ["FaUserCog", "4 roles + administrador por sede", "Paciente, admisionista, médico y auditor"],
      ["FaBan", "Acceso denegado (403) auditado", "Cada intento denegado entra a la cadena"],
      ["FaLink", "Auditoría encadenada SHA-256", "Cada evento firma al anterior"],
      ["FaUserPlus", "Cuenta del paciente", "Contraseña temporal y cambio obligatorio"],
    ];
    filas.forEach(([ic, h, d], i) => {
      const y = 1.4 + i * 1.06;
      circuloIcono(s, I[ic], 0.6, y + 0.05, 0.7, i === 3 ? C.accent2 : BANDA, h);
      texto(s, h, { x: 1.55, y, w: 5.0, h: 0.4, fontSize: 16, bold: true, color: NAVY, valign: "middle" });
      texto(s, d, { x: 1.55, y: y + 0.42, w: 5.0, h: 0.4, fontSize: 14, color: MUTED });
    });
    const hc = altoMarco(S.cuenta, 5.9);
    marco(s, S.cuenta, 6.83, 1.4, 5.9, hc, "Captura: paciente registrado con cuenta y contraseña temporal");
    const w403 = 3.3, h403 = altoMarco(S.denegado, w403);
    marco(s, S.denegado, 8.13, 1.4 + hc + 0.35, w403, h403, "Captura: error 403 acceso denegado");
    s.addNotes(
      "Presenta B (Sharith).\n" +
      "Los permisos se validan en la API, no en la pantalla: cada petición trae un token de sesión (JWT) y cada ruta declara qué roles la pueden usar. Hay cuatro roles más el administrador, que puede ser general o de una sola sede. " +
      "Si alguien intenta algo que no le toca, recibe 403 y el intento queda registrado como ACCESO_DENEGADO. " +
      "La auditoría vive en la base central (pg_central) y es una cadena: cada evento guarda el hash del anterior y su propio hash SHA-256 sobre todos sus campos. " +
      "Y al admitir a un paciente nuevo se le crea su cuenta con una contraseña temporal que se muestra una sola vez; en el primer ingreso debe cambiarla.\n\n" +
      "Pregunta probable: ¿cómo sabe que la auditoría no fue alterada? Respuesta: el verificador recorre la cadena y en cada evento comprueba el índice, el enlace con el anterior y recalcula el hash con los datos actuales. Un UPDATE cambia el contenido pero no puede rehacer el hash sin rehacer toda la cadena; lo detectamos en el índice exacto 3. " +
      "Si piden cambiar un rol en vivo: en app/main.py, vista_reporte, quitar \"paciente\" de requerir_roles, docker compose up -d --build api, y el paciente recibe 403."
    );
  }

  // ============================================================ 9. Vistas
  {
    const s = contenido("Seguridad y vistas", "Cuatro vistas, una por rol");
    const v = [
      [S.paciente, "Paciente · su historia y quién la vio"],
      [S.admision, "Admisión · en qué sedes existe"],
      [S.medico, "Médico · escribe con sello"],
      [S.reporte, "Reporte de HC · 3 sedes, cobertura"],
    ];
    const w = 5.92, h = altoMarco(S.paciente, w);
    v.forEach(([img, lab], i) => {
      const x = 0.6 + (i % 2) * (w + 0.29), y = 1.35 + Math.floor(i / 2) * (h + 0.3);
      marco(s, img, x, y, w, h, "Captura vista " + lab);
      s.addText(lab, { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.19, x: x + 0.18, y: y + h - 0.55, w: 4.1, h: 0.38, fill: { color: NAVY }, color: C.background1, fontSize: 13, bold: true, align: "center", valign: "middle", margin: 0, shadow: sombra(), objectName: "etiqueta " + lab });
    });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "Estas son las cuatro vistas que pide la guía, cada una con lo que su rol puede ver. " +
      "El paciente ve su historia unificada, ordenada por fecha y con la sede de cada atención, descarga su paquete FHIR y ve quién accedió a su historia. " +
      "La admisionista busca por documento y ve en qué sedes existe el paciente, admite y sigue el estado de sus mensajes en el bus; no ve diagnósticos. " +
      "El médico consulta la historia unificada y registra diagnósticos, órdenes y egresos; cada escritura devuelve un sello, que es el hash del evento de auditoría. " +
      "El Reporte de HC agrupa por sede, muestra la cobertura de los 57 campos, el sello del reporte y la pestaña de estado de la plataforma. Todo esto se ve en vivo en el bloque final de la demo."
    );
  }

  // ============================================================ 10. Panel de administración
  {
    const s = contenido("Seguridad y vistas", "Panel de administración en vivo");
    const hl = 5.4, wl = (hl - 0.14) * S.resumen.w / S.resumen.h + 0.14;
    marco(s, S.resumen, 0.6, 1.35, wl, hl, "Captura: panel de administración, resumen y sedes");
    const xr = 0.6 + wl + 0.4, wr = 12.73 - xr;
    const hu = altoMarco(S.usuarios, wr);
    marco(s, S.usuarios, xr, 1.35, wr, hu, "Captura: gestión de usuarios por sede");
    const notas = [
      ["FaTachometerAlt", "Sedes, FHIR, bus y auditoría", "Se actualizan solos cada pocos segundos"],
      ["FaUsers", "Usuarios por sede", "Un administrador de sede solo gestiona la suya"],
    ];
    notas.forEach(([ic, h, d], i) => {
      const y = 1.35 + hu + 0.35 + i * 1.0;
      circuloIcono(s, I[ic], xr, y, 0.6, i === 1 ? C.accent2 : BANDA, h);
      texto(s, h, { x: xr + 0.8, y: y - 0.05, w: wr - 0.8, h: 0.36, fontSize: 15, bold: true, color: NAVY, valign: "middle" });
      texto(s, d, { x: xr + 0.8, y: y + 0.32, w: wr - 0.8, h: 0.55, fontSize: 13, color: MUTED });
    });
    s.addNotes(
      "Presenta B (Sharith).\n" +
      "El administrador tiene un panel que se actualiza solo: sedes activas, estado del servidor FHIR, cobertura FHIR, mensajes recibidos, entregados y rechazados, latencia media del bus y estado de la cadena de auditoría. " +
      "Abajo, cada sede con su motor, su latencia y su cobertura FHIR. " +
      "En la sección de usuarios se crean cuentas por rol y por sede, se desactivan o se restablece la contraseña; un administrador de sede solo ve y crea usuarios de su sede, y el auditor puede consultar pero no gestionar. " +
      "Estas cuentas viven en la base central (pg_central), con contraseña PBKDF2, para que apagar una sede no deje a nadie sin poder entrar."
    );
  }

  // ============================================================ 11. Resiliencia
  pres.addSection({ title: "Resultados" });
  {
    const s = contenido("Resultados", "Resiliencia: probada apagando piezas");
    const cw = 3.87, cx = (i) => 0.6 + i * (cw + 0.26);
    const enc = (i, ic, h, col) => {
      tarjeta(s, cx(i), 1.35, cw, 5.45, "escenario " + h);
      circuloIcono(s, I[ic], cx(i) + 0.25, 1.58, 0.62, col, h);
      texto(s, h, { x: cx(i) + 1.0, y: 1.56, w: cw - 1.15, h: 0.66, fontSize: 16, bold: true, color: NAVY, valign: "middle" });
    };
    enc(0, "FaPowerOff", "Cae la base de Cartagena", C.accent6);
    const iw = cw - 0.4;
    const h1 = altoMarco(S.sedeCaida, iw), h2 = altoMarco(S.incompleto, iw);
    marco(s, S.sedeCaida, cx(0) + 0.2, 2.45, iw, h1, "Captura: sede 2 caída en el panel");
    marco(s, S.incompleto, cx(0) + 0.2, 2.45 + h1 + 0.2, iw, h2, "Captura: reporte incompleto");
    texto(s, "Responde con 2 sedes y avisa\nEstado: DEGRADED · 2 de 3", { x: cx(0) + 0.25, y: 5.7, w: cw - 0.5, h: 0.8, fontSize: 14, bold: true, color: C.accent6 });
    enc(1, "FaRedo", "Servidor FHIR apagado", C.accent2);
    texto(s, "132 s", { x: cx(1) + 0.25, y: 2.45, w: cw - 0.5, h: 1.0, fontFace: HEAD, fontSize: 54, bold: true, color: C.accent2 });
    texto(s, "entregado solo, en el intento 7, sin duplicar", { x: cx(1) + 0.25, y: 3.45, w: cw - 0.5, h: 0.75, fontSize: 15, color: C.text1 });
    const dot = 0.36, gap = (cw - 0.5 - 7 * dot) / 6;
    for (let k = 0; k < 7; k++) {
      const x = cx(1) + 0.25 + k * (dot + gap);
      s.addShape(pres.shapes.OVAL, { x, y: 4.55, w: dot, h: dot, fill: { color: k < 6 ? C.accent6 : C.accent5 }, line: { type: "none" }, objectName: "intento " + (k + 1) });
      texto(s, String(k + 1), { x: x - 0.05, y: 4.95, w: dot + 0.1, h: 0.3, fontSize: 12, color: MUTED, align: "center" });
    }
    texto(s, "intentos · esperas de 2 a 64 s", { x: cx(1) + 0.25, y: 5.3, w: cw - 0.5, h: 0.3, fontSize: 12, color: MUTED });
    texto(s, "129,5 s (10 nov.) · 132,0 s (11 nov.)", { x: cx(1) + 0.25, y: 5.75, w: cw - 0.5, h: 0.6, fontSize: 14, bold: true, color: NAVY });
    enc(2, "FaInbox", "Mensaje MUERTO", C.text1);
    texto(s, "2,6 s", { x: cx(2) + 0.25, y: 2.45, w: cw - 0.5, h: 1.0, fontFace: HEAD, fontSize: 54, bold: true, color: C.accent5 });
    texto(s, "para entregarlo tras reencolar, en 1 intento", { x: cx(2) + 0.25, y: 3.45, w: cw - 0.5, h: 0.75, fontSize: 15, color: C.text1 });
    pastilla(s, "MUERTO", cx(2) + 0.25, 4.45, 1.3, 0.48, C.accent6, C.background1, { fontSize: 12 });
    flecha(s, cx(2) + 1.6, 4.69, cx(2) + 2.2, 4.69, NAVY, "reencolar", 2);
    pastilla(s, "ENTREGADO", cx(2) + 2.25, 4.45, 1.37, 0.48, C.accent5, C.background1, { fontSize: 12 });
    texto(s, "Orden manual: reencolar", { x: cx(2) + 0.25, y: 5.1, w: cw - 0.5, h: 0.35, fontSize: 13, bold: true, color: NAVY });
    texto(s, "Superó 7 intentos con el servidor FHIR apagado; al volver, se reencoló", { x: cx(2) + 0.25, y: 5.65, w: cw - 0.5, h: 0.85, fontSize: 13, color: MUTED });
    s.addNotes(
      "Presenta B (Sharith). Corresponde a los bloques 5, 6 y 7 de la demo.\n" +
      "Probamos la resiliencia apagando piezas de verdad. Primero, docker stop mongo_sede2: la consulta del paciente 1001 responde con Sincelejo y Corozal, marca el reporte como incompleto y el estado de salud (/health) pasa a DEGRADED con 2 de 3 nodos; al encender el contenedor vuelve Cartagena. " +
      "Segundo, con el servidor FHIR apagado (docker compose stop hapi-fhir) enviamos un mensaje: el bus responde reintentando, sigue intentando con esperas crecientes y lo entregó solo en el intento 7, a los 132 segundos, sin duplicar. " +
      "Tercero, si el servidor FHIR tarda más que la ventana de reintentos el mensaje queda MUERTO; con el servidor de nuevo arriba, POST /hsb/reencolar/{id} lo entregó en 2,6 segundos.\n\n" +
      "Pregunta probable: ¿por qué los errores de datos no se reintentan? Respuesta: reintentar sirve para fallas transitorias. Una restricción violada o un rechazo 4xx del servidor FHIR fallará igual en el intento 7; solo gastaría dos minutos de cola. Esos se marcan como permanentes y van directo a MUERTO con su motivo."
    );
  }

  // ============================================================ 12. Resultados medidos
  {
    const s = contenido("Resultados", "Resultados medidos");
    const tiles = [
      ["FaCheckCircle", "0", "errores FHIR", "validación oficial · 26 recursos", C.accent5],
      ["FaClipboardList", "56/57", "campos del mensaje completo", "100 % de los obligatorios", NAVY],
      ["FaLayerGroup", "52/57", "campos del paciente 1001", "3 sedes, 2 motores, 100 % obligatorios", NAVY],
      ["FaClone", "1", "paciente 1007 tras reenviar", "el bus respondió «duplicado»", NAVY],
      ["FaUndo", "ROLLBACK", "ACID en PostgreSQL", "regla violada: sin usuario huérfano", C.accent3],
      ["FaVial", "44/44", "pruebas automatizadas", "pytest, en 8,78 s", C.accent5],
      ["FaExchangeAlt", "148", "mensajes de prueba", "135 entregados · 8 rechazados · 5 duplicados", NAVY],
      ["FaLink", "Índice 3", "auditoría alterada", "detectada por el verificador de la cadena", C.accent2],
    ];
    const w = 2.86, h = 2.55, gx = (12.13 - 4 * w) / 3;
    tiles.forEach(([ic, n, l, d, col], i) => {
      const x = 0.6 + (i % 4) * (w + gx), y = 1.35 + Math.floor(i / 4) * (h + 0.25);
      tarjeta(s, x, y, w, h, "resultado " + l);
      circuloIcono(s, I[ic], x + 0.25, y + 0.22, 0.5, col === NAVY ? BANDA : col, l);
      const largo = n.length > 5;
      texto(s, n, { x: x + 0.25, y: y + 0.75, w: w - 0.4, h: 0.72, fontFace: HEAD, fontSize: largo ? 26 : 40, bold: true, color: col, valign: "middle" });
      texto(s, l, { x: x + 0.25, y: y + 1.5, w: w - 0.4, h: 0.5, fontSize: 14, bold: true, color: C.text1 });
      texto(s, d, { x: x + 0.25, y: y + 2.0, w: w - 0.4, h: 0.48, fontSize: 12, color: MUTED });
    });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "Estos números son medidos en Kali Linux, en una máquina virtual de 3,8 GB con Docker 28, el 10 y 11 de noviembre. " +
      "El paquete FHIR del paciente 1001 pasó la validación oficial ($validate) con 0 errores. El mensaje completo cubre 56 de 57 campos y la historia real de 1001, desde tres sedes y dos motores, 52 de 57, siempre con el 100 % de los obligatorios. " +
      "Reenviar el ejemplo 01 dejó un solo Patient 1007. La demo de ACID en PostgreSQL (db/demo_acid.sql) hace rollback completo cuando se viola un CHECK. Pasan las 44 pruebas automatizadas. " +
      "Para las capturas cargamos 148 mensajes: 135 entregados, 8 rechazados a propósito y 5 duplicados. Y el UPDATE sobre la auditoría se detectó en el índice 3. " +
      "Lo que no medimos de forma sistemática es la latencia y los mensajes por minuto bajo carga; los contadores de /metrics son de una sesión de demo, no una prueba de carga.\n\n" +
      "Pregunta probable: ¿cómo se calcula la cobertura? Respuesta: hay dos. La FHIR por sede es pacientes con fhir_patient_id sobre pacientes de la sede (0 % al inicio). La de 57 campos cuenta un campo como cubierto si tiene valor en el usuario o en alguna atención de cualquier sede."
    );
  }

  // ============================================================ 13. Guion de la demo
  pres.addSection({ title: "Demo y cierre" });
  {
    const s = contenido("Demo y cierre", "Guion de la demostración en vivo");
    const pasos = [
      ["00:00", "A", "Arranque limpio desde cero", "Un solo comando, con las bases vacías"],
      ["02:00", "B", "Cobertura FHIR en 0 %", "Tablero del auditor: 0 % en las 3 sedes"],
      ["03:00", "A", "Entran HL7 y CSV; sube la cobertura", "2 HL7 válidos, 1 inválido y 1 archivo CSV"],
      ["05:30", "B", "Reenvío: el bus responde duplicado", "Mismo mensaje: 1 solo paciente 1007"],
      ["07:30", "B", "Cae la base de Cartagena", "Reporte incompleto y luego se recupera"],
      ["10:30", "B", "Auditoría alterada y detectada", "Se cambia un evento: alerta en el índice 3"],
      ["12:00", "A+B", "Consulta unificada y Reporte de HC", "Paciente 1001: 3 sedes, 52/57 campos"],
    ];
    const y0 = 1.35, rh = 0.72;
    s.addShape(pres.shapes.LINE, { x: 0.84, y: y0 + 0.24, w: 0, h: rh * 6, line: { color: LINEA, width: 2 }, objectName: "línea de tiempo" });
    pasos.forEach(([min, quien, t, cmd], i) => {
      const y = y0 + i * rh;
      s.addText(String(i + 1), { shape: pres.shapes.OVAL, x: 0.6, y, w: 0.48, h: 0.48, fill: { color: BANDA }, color: C.background1, bold: true, fontSize: 15, align: "center", valign: "middle", margin: 0, objectName: "paso " + (i + 1) });
      texto(s, min, { x: 1.3, y, w: 0.85, h: 0.48, fontSize: 14, color: MUTED, valign: "middle", bold: true });
      pastilla(s, quien, 2.2, y + 0.04, 0.68, 0.4, quien === "B" ? NAVY : AZUL_MEDIO, C.background1, { fontSize: 12 });
      texto(s, t, { x: 3.1, y, w: 4.1, h: 0.48, fontSize: 15, bold: true, color: NAVY, valign: "middle" });
      texto(s, cmd, { x: 7.35, y, w: 5.38, h: 0.48, fontSize: 13, color: C.text1, valign: "middle", fill: { color: C.background2 }, line: { color: LINEA, width: 0.75 }, margin: 6 });
    });
    texto(s, "Intercalado (A): mensaje de 57 campos con el servidor FHIR apagado a las 06:30; se ve entregado a las 09:30 (56/57).", { x: 0.6, y: 6.4, w: 11.6, h: 0.35, fontSize: 12, color: MUTED, italic: true });
    s.addNotes(
      "Presentan A y B. Esta diapositiva queda de fondo como mapa de la demo.\n" +
      "1 (A): docker compose down -v && docker compose up -d --build; docker compose ps; curl -s http://localhost:8001/health | jq. " +
      "2 (B): entrar como auditor_elena en localhost:8000/login y abrir localhost:8000/reporte?pestana=tablero: cobertura FHIR 0 %. " +
      "3 (A): POST /hsb/hl7 con ejemplos 01, 02 y 03 y POST /hsb/csv?sede=3 con el ejemplo 04 (3 entregados, 2 rechazados); la cobertura sube: sede 1 50 %, sede 2 33,3 %, sede 3 75 %. " +
      "4 (B): reenviar el ejemplo 01 → duplicado; curl \"localhost:8090/fhir/Patient?identifier=1007&_summary=count\" da 1, y countDocuments en mongo_sede2 da 1. " +
      "Intercalado (A): docker compose stop hapi-fhir, enviar tests/datos/06_adt_a03_57_campos_sede1.hl7 (queda reintentando) y docker compose start hapi-fhir. " +
      "5 (B): como medico_mateo buscar 1001; docker stop mongo_sede2; reporte incompleto y /health DEGRADED 2/3; docker start mongo_sede2. " +
      "6 (B): como paciente_carlos abrir /api/pacientes/1002/historia → 403; docker exec -it pg_central psql -U clinica_user -d clinica_central -c \"UPDATE evento_auditoria SET usuario_sistema='intruso' WHERE indice = 3\"; el tablero marca el índice 3. " +
      "7 (A+B): A abre localhost:8000/reporte?buscar_doc=1001 (3 sedes, 52/57, sello); B registra un diagnóstico CIE-10 como médico y muestra el sello.\n" +
      "Si algo falla: si el mensaje de 57 campos queda MUERTO, curl -X POST localhost:8001/hsb/reencolar/MSG-0057; si el ejemplo 01 sale duplicado la primera vez, faltó el down -v."
    );
  }

  // ============================================================ 14. Limitaciones
  {
    const s = contenido("Demo y cierre", "Limitaciones y trabajo futuro");
    texto(s, "Hoy", { x: 0.6, y: 1.3, w: 5.5, h: 0.35, fontSize: 15, bold: true, color: C.accent2 });
    texto(s, "Siguiente paso", { x: 7.0, y: 1.3, w: 5.5, h: 0.35, fontSize: 15, bold: true, color: NAVY });
    const filas = [
      ["MongoDB sin replica set", "Replica set y versión del documento"],
      ["Bus de integración sin autenticación", "Keycloak / OIDC y TLS entre servicios"],
      ["Un solo servidor FHIR", "Varios servidores FHIR sobre PostgreSQL"],
      ["Latencia no medida con carga", "Prueba de carga: latencia y mensajes/min"],
      ["Kubernetes sin probar en Minikube", "Kubernetes en Minikube y CI (44 pruebas)"],
    ];
    filas.forEach(([a, b], i) => {
      const y = 1.75 + i * 0.98;
      caja(s, 0.6, y, 5.7, 0.78, T_AMBAR, null, "limitación " + a, 0.08);
      s.addImage({ data: IA.FaExclamationTriangle, x: 0.85, y: y + 0.22, w: 0.34, h: 0.34, altText: "limitación", objectName: "icono limitación " + (i + 1) });
      texto(s, a, { x: 1.4, y, w: 4.8, h: 0.78, fontSize: 15, color: C.text1, valign: "middle" });
      flecha(s, 6.4, y + 0.39, 6.9, y + 0.39, NAVY, "flecha " + (i + 1), 2);
      tarjeta(s, 7.0, y, 5.73, 0.78, "futuro " + b);
      circuloIcono(s, I.FaCheckCircle, 7.2, y + 0.17, 0.44, BANDA, "futuro " + (i + 1));
      texto(s, b, { x: 7.8, y, w: 4.85, h: 0.78, fontSize: 15, color: C.text1, valign: "middle" });
    });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "Queremos ser honestos con lo que el prototipo no resuelve. MongoDB corre sin replica set: no hay conmutación por fallo ni transacciones multi-documento. " +
      "El bus de integración (hsb_bus, puerto 8001) no exige autenticación; solo el portal y API la exige. Hay un solo servidor FHIR (hapi_fhir_r4) con su base embebida. No medimos latencia ni mensajes por minuto con una prueba de carga. " +
      "Y aunque dejamos manifiestos de Kubernetes para Minikube (infra/k8s), no presentamos evidencia de que corran. " +
      "El trabajo futuro sale directo de esa lista: replica set, Keycloak con TLS, varios servidores FHIR sobre PostgreSQL, una prueba de carga y un pipeline de CI que corra las 44 pruebas.\n\n" +
      "Pregunta probable: ¿qué pasa si alguien con acceso a la base central rehace toda la cadena? Respuesta: puede hacerlo; por eso el trabajo futuro incluye anclar periódicamente el último hash fuera del sistema, por ejemplo en Hyperledger Fabric."
    );
  }

  // ============================================================ 15. Cierre
  {
    const s = pres.addSlide({ masterName: "CIERRE", sectionTitle: "Demo y cierre" });
    texto(s, [
      { text: "¡Muchas Gracias!", options: { fontSize: 22, bold: true, color: NAVY } },
      { text: "  ·  Espacio de preguntas", options: { fontSize: 20, color: NAVY } },
    ], { x: 2.17, y: 4.66, w: 9.0, h: 0.45, fontFace: HEAD, align: "center", valign: "middle" });
    texto(s, "Demo en vivo: http://192.168.1.94:8000 · Repositorio con etiqueta v1.0", { x: 2.67, y: 6.08, w: 8.0, h: 0.3, fontSize: 12, color: MUTED, align: "center" });
    s.addNotes(
      "Presenta B (Sharith).\n" +
      "Para cerrar: un catálogo de 57 campos, un registro común y entregas que no duplican bastaron para unificar tres sedes con motores distintos, sin transacción distribuida y sin tocar los sistemas legados. " +
      "La demo está corriendo en http://192.168.1.94:8000 y el código está en github.com/jose18000/Parcial-Final-Sistemas-Distribuidos-Plataforma-de-Interoperabilidad-en-Salud con la etiqueta v1.0; el README tiene todos los pasos y los usuarios de prueba. " +
      "Gracias. Quedamos atentos a sus preguntas; las respondemos los dos.\n\n" +
      "Reparto de preguntas (para no pisarse): A lidera CAP con la sede caída, auditoría, escalar 100×, bus caído entre FHIR y sede, errores de datos. B lidera duplicados, cambio de rol en vivo, por qué MongoDB, viaje de un campo y cobertura."
    );
  }

  await pres.writeFile({ fileName: SALIDA });
  await aplicarTema(SALIDA, THEME);
  console.log("Escrito:", SALIDA);
}

// Escribe los colores del tema en ppt/theme/theme1.xml (pptxgenjs deja la paleta de Office).
async function aplicarTema(archivo, tema) {
  const p = process.env.PPTX_APPLY_THEME;
  if (p && fs.existsSync(p)) { await require(p).applyTheme(archivo, tema); return; }
  const JSZip = require(require.resolve("jszip", { paths: [require.resolve("pptxgenjs")] }));
  const zip = await JSZip.loadAsync(fs.readFileSync(archivo));
  const parte = "ppt/theme/theme1.xml";
  const SLOTS = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"];
  const esquema = `<a:clrScheme name="${tema.name}">` + SLOTS.map((k) => `<a:${k}><a:srgbClr val="${tema.colors[k]}"/></a:${k}>`).join("") + "</a:clrScheme>";
  let xml = await zip.file(parte).async("string");
  xml = xml.replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => esquema)
    .replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, h) => `${h}${tema.name}"`);
  zip.file(parte, xml);
  for (const f of Object.keys(zip.files).filter((n) => /^ppt\/charts\/chart\d+\.xml$/.test(n))) {
    const c = await zip.file(f).async("string");
    zip.file(f, c.replace(/<c:crossesAt val="autoZero"\/>/g, '<c:crosses val="autoZero"/>'));
  }
  fs.writeFileSync(archivo, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

construir().catch((e) => { console.error(e); process.exit(1); });
