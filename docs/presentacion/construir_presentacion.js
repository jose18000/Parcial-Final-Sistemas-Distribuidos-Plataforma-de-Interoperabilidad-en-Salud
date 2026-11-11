// Genera docs/presentacion/Presentacion_Sustentacion.pptx
// Sustentación del parcial final de Sistemas Distribuidos (15 min + 10 min de preguntas).
//
// Requisitos (no se instalan dentro del proyecto): pptxgenjs, react, react-dom, react-icons, sharp.
//   npm install pptxgenjs react react-dom react-icons sharp      (en una carpeta aparte)
//   NODE_PATH=<esa carpeta>/node_modules node docs/presentacion/construir_presentacion.js
//
// Todas las imágenes salen del repositorio (docs/capturas, app/static); los recortes se hacen
// en memoria con sharp, así que el script se puede volver a correr sin archivos intermedios.

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

// ---------------------------------------------------------------- tema
const THEME = {
  name: "Interoperabilidad Clinica",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "10222B", lt1: "FFFFFF", dk2: "0B4F59", lt2: "E6F4F6",
    accent1: "0F6B78", accent2: "C8820A", accent3: "2F6FB0", accent4: "3F8F3A",
    accent5: "1E7E34", accent6: "C82333", hlink: "0F6B78", folHlink: "51606B",
  },
};
const HEX = THEME.colors;
const MUTED = "51606B";
const LINEA = "D3E2E6";
const SUAVE = "F3F8F9";
const T_AMBAR = "FBF1DE";
const T_AZUL = "E8F0F9";
const T_VERDE = "EAF4E9";
const T_ROJO = "FBE9EB";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Plataforma distribuida de interoperabilidad clínica";
pres.subject = "Sustentación · Sistemas Distribuidos";
pres.author = "Jose Guillermo Canchila · Sharit Javier Manjarrez";
pres.company = "Sistemas Distribuidos";
const C = pres.SchemeColor;
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
  return { type: "outer", color: "10222B", opacity: 0.18, blur: 8, offset: 2, angle: 90 };
}

// Marco redondeado con sombra suave y la captura dentro.
function marco(slide, img, x, y, w, h, nombre) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.1, fill: { color: C.background1 },
    line: { color: LINEA, width: 0.75 }, shadow: sombra(), objectName: nombre + " marco",
  });
  const p = 0.07;
  // encajar manteniendo proporción
  const bw = w - 2 * p, bh = h - 2 * p;
  const r = img.w / img.h;
  let iw = bw, ih = bw / r;
  if (ih > bh) { ih = bh; iw = bh * r; }
  slide.addImage({
    data: img.data, x: x + p + (bw - iw) / 2, y: y + p + (bh - ih) / 2, w: iw, h: ih,
    altText: nombre, objectName: nombre,
  });
}

// Alto que ocupa un marco de ancho w para una imagen.
function altoMarco(img, w) { return (w - 0.14) * img.h / img.w + 0.14; }

function circuloIcono(slide, icono, x, y, d, fill, nombre) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill || C.accent1 }, line: { type: "none" }, objectName: nombre + " círculo" });
  const k = d * 0.52;
  slide.addImage({ data: icono, x: x + (d - k) / 2, y: y + (d - k) / 2, w: k, h: k, altText: nombre, objectName: nombre + " icono" });
}

function flecha(slide, x1, y1, x2, y2, color, nombre, ancho = 1.75) {
  slide.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipH: x2 < x1, flipV: y2 < y1,
    line: { color: color || C.accent1, width: ancho, endArrowType: "triangle" }, objectName: nombre,
  });
}

function caja(slide, x, y, w, h, fill, linea, nombre, radio = 0.08) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: radio, fill: { color: fill },
    line: linea ? { color: linea, width: 1 } : { type: "none" }, objectName: nombre,
  });
}

function pastilla(slide, t, x, y, w, h, fill, color, o = {}) {
  slide.addText(t, Object.assign({
    shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: h / 2, x, y, w, h, fill: { color: fill },
    color, fontSize: 13, bold: true, align: "center", valign: "middle", margin: 0, objectName: "pastilla " + (typeof t === "string" ? t : ""),
  }, o));
}

// ---------------------------------------------------------------- layouts
function definirLayouts(fondo) {
  pres.defineSlideMaster({
    title: "PORTADA",
    background: { color: C.text2 },
    objects: [
      { image: { data: fondo, x: 0, y: 0, w: 13.333, h: 7.5, sizing: { type: "cover", w: 13.333, h: 7.5 } } },
      { rect: { x: 0, y: 0, w: 13.333, h: 7.5, fill: { color: "0B4F59", transparency: 22 }, line: { type: "none" } } },
      { rect: { x: 0, y: 0, w: 8.6, h: 7.5, fill: { color: "082F36", transparency: 35 }, line: { type: "none" } } },
      { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 1.9, w: 7.6, h: 1.9, fontFace: HEAD, fontSize: 40, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.95, w: 7.6, h: 0.6, fontSize: 22, color: C.background2, valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENIDO",
    background: { color: C.background1 },
    margin: [0.4, 0.6, 0.5, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.13, h: 0.85, fontFace: HEAD, fontSize: 34, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { text: { text: "Interoperabilidad clínica · Red de IPS Sincelejo · Cartagena · Corozal", options: { x: 0.6, y: 7.03, w: 8, h: 0.3, fontSize: 10, color: MUTED, margin: 0 } } },
    ],
    slideNumber: { x: 12.23, y: 7.03, w: 0.5, h: 0.3, fontSize: 10, color: MUTED, align: "right", margin: 0 },
  });
}

// ---------------------------------------------------------------- diapositivas
async function construir() {
  const fondoBuf = await sharp(path.join(RAIZ, "app", "static", "img", "login-hero.jpg")).jpeg({ quality: 85 }).toBuffer();
  definirLayouts("image/jpeg;base64," + fondoBuf.toString("base64"));
  const logoBuf = await sharp(path.join(RAIZ, "app", "static", "logo.svg")).resize(256, 256).png().toBuffer();
  const LOGO = "image/png;base64," + logoBuf.toString("base64");

  const I = {};
  for (const n of ["FaHospital", "FaDatabase", "FaLeaf", "FaExchangeAlt", "FaShieldAlt", "FaKey", "FaUserShield", "FaLock",
    "FaLink", "FaRedo", "FaCheckCircle", "FaFileMedical", "FaUsers", "FaUserMd", "FaClipboardList", "FaBolt", "FaClock",
    "FaHeartbeat", "FaCode", "FaBan", "FaHashtag", "FaUserPlus", "FaLayerGroup", "FaDocker", "FaFingerprint",
    "FaExclamationTriangle", "FaPlug", "FaInbox", "FaTachometerAlt", "FaCubes", "FaIdCard", "FaUserCog", "FaStethoscope",
    "FaFileAlt", "FaPuzzlePiece", "FaBalanceScale", "FaUndo", "FaTable", "FaClone", "FaVial", "FaHistory", "FaSitemap",
    "FaPowerOff", "FaRandom", "FaServer", "FaDesktop", "FaGithub", "FaNetworkWired"]) {
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

  const contenido = (seccion, titulo) => {
    const s = pres.addSlide({ masterName: "CONTENIDO", sectionTitle: seccion });
    s.addText(titulo, { placeholder: "title" });
    return s;
  };

  // ============================================================ 1. Portada
  pres.addSection({ title: "Apertura" });
  {
    const s = pres.addSlide({ masterName: "PORTADA", sectionTitle: "Apertura" });
    s.addImage({ data: LOGO, x: 0.8, y: 0.75, w: 0.75, h: 0.75, altText: "Logo de la plataforma", objectName: "logo" });
    texto(s, "SUSTENTACIÓN · PARCIAL FINAL", { x: 1.75, y: 0.95, w: 6, h: 0.4, fontSize: 14, bold: true, color: C.background2, charSpacing: 2, valign: "middle" });
    s.addText("Plataforma distribuida de interoperabilidad clínica", { placeholder: "title" });
    s.addText("Red de IPS Sincelejo · Cartagena · Corozal", { placeholder: "body" });
    texto(s, [
      { text: "Jose Guillermo Canchila (A) · Sharit Javier Manjarrez (B)", options: { breakLine: true, bold: true } },
      { text: "Sistemas Distribuidos · Noviembre de 2026" },
    ], { x: 0.8, y: 5.35, w: 7.6, h: 0.8, fontSize: 16, color: C.background1, paraSpaceAfter: 4 });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "Buenos días. Somos Jose Guillermo Canchila y Sharit Javier Manjarrez y vamos a sustentar la plataforma distribuida de interoperabilidad clínica para la red de IPS de Sincelejo, Cartagena y Corozal. " +
      "En 15 minutos vamos a alternar diapositivas cortas con la demostración en vivo, siguiendo el orden de la guía de la Fase 5: arranque limpio, cobertura en 0 %, mensajes HL7 y CSV, duplicado, caída de una sede, auditoría alterada y consulta unificada. " +
      "Mientras hablo, B deja corriendo el arranque limpio con docker compose down -v y up -d --build, porque HAPI tarda unos 90 segundos en responder."
    );
  }

  // ============================================================ 2. El problema
  {
    const s = contenido("Apertura", "Una historia clínica partida en tres sedes");
    const sedes = [
      ["Sede 1 · Sincelejo", "PostgreSQL", "HL7 v2 ORU^R01", C.accent3, T_AZUL, "FaDatabase"],
      ["Sede 2 · Cartagena", "MongoDB", "HL7 v2 ADT^A01", C.accent4, T_VERDE, "FaLeaf"],
      ["Sede 3 · Corozal", "PostgreSQL", "CSV legado con ;", C.accent3, T_AZUL, "FaDatabase"],
    ];
    sedes.forEach(([nom, motor, fmt, col, tinte, ic], i) => {
      const y = 1.6 + i * 1.75;
      caja(s, 0.6, y, 5.3, 1.4, SUAVE, LINEA, "tarjeta " + nom);
      circuloIcono(s, I[ic], 0.85, y + 0.3, 0.8, col, nom);
      texto(s, nom, { x: 1.9, y: y + 0.22, w: 3.8, h: 0.42, fontSize: 20, bold: true, valign: "middle" });
      pastilla(s, motor, 1.9, y + 0.78, 1.45, 0.38, tinte, col, { fontSize: 13 });
      texto(s, fmt, { x: 3.5, y: y + 0.78, w: 2.3, h: 0.38, fontSize: 14, color: MUTED, valign: "middle" });
      flecha(s, 5.9, y + 0.7, 7.15, 3.95, C.accent1, "flecha " + nom, 2);
    });
    caja(s, 7.3, 1.85, 5.43, 4.2, C.background2, null, "meta", 0.12);
    circuloIcono(s, I.FaFileMedical, 7.65, 2.2, 0.95, C.accent1, "historia unificada");
    texto(s, "Una sola historia, sin reemplazar los legados", { x: 8.8, y: 2.2, w: 3.7, h: 0.95, fontFace: HEAD, fontSize: 22, bold: true, color: C.text2, valign: "middle" });
    const metas = [
      ["FaClipboardList", "57 campos de la Res. 866 de 2021"],
      ["FaExchangeAlt", "Publicada en FHIR R4"],
      ["FaShieldAlt", "Cada acceso queda auditado"],
    ];
    metas.forEach(([ic, t], i) => {
      const y = 3.55 + i * 0.75;
      circuloIcono(s, I[ic], 7.75, y, 0.5, C.text2, t);
      texto(s, t, { x: 8.45, y, w: 4.1, h: 0.5, fontSize: 17, valign: "middle", color: C.text1 });
    });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "El problema: la red tiene tres sedes y cada una conserva su sistema legado, con su propia base y su propio motor. Sincelejo y Corozal usan PostgreSQL; Cartagena, MongoDB. " +
      "Además envían en formatos distintos: Sincelejo y Cartagena mandan HL7 v2, Corozal exporta un CSV separado por punto y coma. " +
      "El resultado es que la historia de un mismo paciente queda partida en tres. " +
      "La meta fue unificarla con los 57 campos de la Resolución 866 de 2021 y publicarla en FHIR R4, sin pedirle a ninguna sede que cambie su sistema."
    );
  }

  // ============================================================ 3. Arquitectura
  pres.addSection({ title: "Arquitectura" });
  {
    const s = contenido("Arquitectura", "Siete contenedores, un solo comando");
    texto(s, "Sistemas legados", { x: 0.6, y: 1.5, w: 2.3, h: 0.35, fontSize: 12, bold: true, color: MUTED });
    const leg = [["Sede 1 · HL7 ORU", C.accent3], ["Sede 2 · HL7 ADT", C.accent4], ["Sede 3 · CSV", C.accent3]];
    leg.forEach(([t, col], i) => {
      const y = 1.95 + i * 0.85;
      pastilla(s, t, 0.6, y, 2.2, 0.6, C.background1, col, { line: { color: col, width: 1.25 }, fontSize: 13 });
      flecha(s, 2.8, y + 0.3, 3.4, 3.3, MUTED, "entrada " + t, 1.25);
    });
    // HSB
    s.addText([
      { text: "hsb_bus :8001", options: { bold: true, fontSize: 17, breakLine: true } },
      { text: "traductor de 57 campos · valida · idempotencia · reintentos", options: { fontSize: 12 } },
    ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, x: 3.4, y: 2.55, w: 3.0, h: 1.5, fill: { color: C.text2 }, color: C.background1, align: "center", valign: "middle", margin: 6, objectName: "hsb_bus" });
    // HAPI
    s.addText([
      { text: "hapi_fhir_r4 :8090", options: { bold: true, fontSize: 17, breakLine: true } },
      { text: "FHIR R4 · Bundle transaction con PUT", options: { fontSize: 12 } },
    ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, x: 7.15, y: 2.55, w: 2.75, h: 1.5, fill: { color: C.accent1 }, color: C.background1, align: "center", valign: "middle", margin: 6, objectName: "hapi_fhir_r4" });
    flecha(s, 6.4, 3.3, 7.15, 3.3, C.text2, "hsb a hapi", 2);
    texto(s, "1º", { x: 6.55, y: 2.92, w: 0.5, h: 0.3, fontSize: 12, bold: true, color: C.text2, align: "center" });
    // Sedes
    const sedes = [["pg_sede1", "PostgreSQL · Sincelejo", C.accent3, T_AZUL, 2.85], ["mongo_sede2", "MongoDB · Cartagena", C.accent4, T_VERDE, 5.1], ["pg_sede3", "PostgreSQL · Corozal", C.accent3, T_AZUL, 7.35]];
    sedes.forEach(([n, d, col, tinte, x]) => {
      s.addText([
        { text: n, options: { bold: true, fontSize: 15, breakLine: true, color: col } },
        { text: d, options: { fontSize: 12, color: C.text1 } },
      ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, x, y: 5.25, w: 2.05, h: 1.05, fill: { color: tinte }, line: { color: col, width: 1.25 }, align: "center", valign: "middle", margin: 4, objectName: n });
      flecha(s, 4.9, 4.05, x + 1.025, 5.25, C.text2, "hsb a " + n, 1.5);
    });
    texto(s, "2º UPSERT por sede", { x: 1.0, y: 4.45, w: 2.6, h: 0.3, fontSize: 12, bold: true, color: C.text2, align: "right" });
    // API
    pastilla(s, "4 vistas por rol", 10.3, 1.45, 2.43, 0.55, C.background1, C.text1, { line: { color: MUTED, width: 1 }, fontSize: 13 });
    flecha(s, 11.515, 2.0, 11.515, 2.55, MUTED, "vistas a api", 1.5);
    s.addText([
      { text: "api_gateway :8000", options: { bold: true, fontSize: 16, breakLine: true } },
      { text: "JWT · roles · consulta unificada en paralelo", options: { fontSize: 12 } },
    ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, x: 10.3, y: 2.55, w: 2.43, h: 1.5, fill: { color: C.background2 }, line: { color: C.accent1, width: 1.5 }, color: C.text1, align: "center", valign: "middle", margin: 6, objectName: "api_gateway" });
    s.addText([
      { text: "pg_central", options: { bold: true, fontSize: 15, breakLine: true, color: C.accent2 } },
      { text: "auditoría SHA-256 · cuentas", options: { fontSize: 12, color: C.text1 } },
    ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.1, x: 10.3, y: 5.25, w: 2.43, h: 1.05, fill: { color: T_AMBAR }, line: { color: C.accent2, width: 1.25 }, align: "center", valign: "middle", margin: 4, objectName: "pg_central" });
    flecha(s, 11.515, 4.05, 11.515, 5.25, C.accent2, "api a pg_central", 1.5);
    flecha(s, 10.3, 3.9, 9.4, 5.25, C.accent1, "api a sedes", 1.5);
    texto(s, "lee las 3 sedes en paralelo", { x: 6.95, y: 4.45, w: 2.65, h: 0.3, fontSize: 12, bold: true, color: C.accent1, align: "right" });
    // comando
    circuloIcono(s, I.FaDocker, 0.6, 6.42, 0.45, C.text2, "docker");
    texto(s, "docker compose down -v && docker compose up -d --build", { x: 1.2, y: 6.42, w: 7.5, h: 0.45, fontFace: MONO, fontSize: 14, color: C.text2, valign: "middle", bold: true });
    s.addNotes(
      "Presenta A (Jose), mientras HAPI termina de arrancar (bloque 1 del guion).\n" +
      "Son siete contenedores que suben con un solo comando desde volúmenes vacíos. Las tres sedes, cada una con su motor: pg_sede1, mongo_sede2 y pg_sede3. " +
      "El HSB, en el puerto 8001, recibe HL7, CSV y JSON, traduce al registro de 57 campos, valida, controla duplicados y reintenta. Entrega primero a HAPI FHIR y después a la sede. " +
      "La API, en el 8000, valida el JWT y los permisos y sirve las cuatro vistas; la consulta unificada pregunta a las tres sedes en paralelo. pg_central guarda solo la auditoría encadenada y las cuentas. " +
      "Regla de oro: ninguna vista habla con las bases; lecturas por la API, escrituras por el HSB.\n\n" +
      "Pregunta probable: ¿qué escalaría primero con 100 veces más mensajes? Respuesta: el HSB. Pondríamos un broker (Kafka o RabbitMQ, una partición por sede) y varias réplicas del bus; ya son casi sin estado porque la idempotencia vive en mensaje_bus de cada sede. Después HAPI en varias instancias y al final réplicas de lectura en las sedes."
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
      caja(s, x, 1.5, 3.87, 3.3, tinte, null, "tarjeta " + nom, 0.1);
      circuloIcono(s, I[ic], x + 0.25, 1.75, 0.7, col, motor);
      texto(s, nom, { x: x + 1.1, y: 1.72, w: 2.65, h: 0.38, fontSize: 17, bold: true, valign: "middle" });
      texto(s, motor, { x: x + 1.1, y: 2.1, w: 2.65, h: 0.36, fontSize: 16, bold: true, color: col, valign: "middle" });
      if (tipo === "tabla") {
        for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) {
          s.addShape(pres.shapes.RECTANGLE, { x: x + 0.3 + c * 0.82, y: 2.75 + r * 0.3, w: 0.8, h: 0.28, fill: { color: r === 0 ? col : C.background1 }, line: { color: col, width: 0.5 }, objectName: "celda" });
        }
      } else {
        texto(s, '{ _id: "1007",\n  identificacion: {…},\n  atenciones: [ {…} ] }', { x: x + 0.3, y: 2.7, w: 3.3, h: 0.95, fontFace: MONO, fontSize: 12, color: C.text1, fill: { color: C.background1 }, margin: 6 });
      }
      texto(s, desc, { x: x + 0.3, y: 3.8, w: 3.3, h: 0.9, fontSize: 14, color: C.text1 });
    });
    const ideas = [
      ["FaPuzzlePiece", "Persistencia políglota", "Un repositorio con una sola interfaz para los dos motores"],
      ["FaUndo", "ACID dentro de cada sede", "Sin 2PC entre sedes: cada nodo es atómico por sí solo"],
      ["FaBalanceScale", "CAP: AP en las lecturas", "Si una sede cae, se responde con las otras y se avisa"],
    ];
    ideas.forEach(([ic, h, d], i) => {
      const x = 0.6 + i * 4.13;
      circuloIcono(s, I[ic], x, 5.2, 0.62, C.accent1, h);
      texto(s, h, { x: x + 0.8, y: 5.12, w: 3.05, h: 0.4, fontSize: 16, bold: true, color: C.text2, valign: "middle" });
      texto(s, d, { x: x + 0.8, y: 5.52, w: 3.05, h: 0.9, fontSize: 14, color: MUTED });
    });
    s.addNotes(
      "Presenta B (Sharit).\n" +
      "El escenario dice que cada sede conserva su sistema, y el docente pidió que no todas usaran el mismo motor. Elegimos MongoDB para Cartagena porque es el caso más distinto de un relacional: un documento por paciente, con las atenciones embebidas y otros nombres de campo. " +
      "Si la plataforma funciona con eso, no depende de un esquema único. Para el bus y la consulta los dos motores se ven igual: un repositorio con la misma interfaz. " +
      "La atomicidad es local: en PostgreSQL, una transacción; en MongoDB, una escritura de un documento. No usamos transacción distribuida. " +
      "En las lecturas elegimos disponibilidad: si una sede no responde, se devuelve lo de las otras con el reporte marcado como incompleto.\n\n" +
      "Pregunta probable: si la sede 2 cae a mitad de una transacción, ¿qué garantiza y qué sacrifica? Respuesta: dentro de la sede, o queda el documento nuevo o el anterior, nunca media atención. Entre HAPI y la sede hay consistencia eventual con reintentos idempotentes. Se sacrifica consistencia mientras dura la partición: el médico no ve Cartagena, pero el sistema le avisa."
    );
  }

  // ============================================================ 5. Traductor 57 campos
  {
    const s = contenido("Arquitectura", "Un traductor universal de 57 campos");
    texto(s, "Viaje del campo 14 · municipio de residencia (código DANE)", { x: 0.6, y: 1.35, w: 12, h: 0.4, fontSize: 16, color: MUTED, italic: true });
    const nodo = (x, y, w, h, et, val, col, tinte, nombre) => {
      caja(s, x, y, w, h, tinte, col, nombre, 0.08);
      texto(s, et, { x: x + 0.15, y: y + 0.12, w: w - 0.3, h: 0.32, fontSize: 13, bold: true, color: col });
      texto(s, val, { x: x + 0.15, y: y + 0.45, w: w - 0.3, h: h - 0.55, fontFace: MONO, fontSize: 12, color: C.text1 });
    };
    nodo(0.6, 2.3, 2.35, 1.3, "HL7 v2.5", "PID-11.9\n\"70001\"", C.text2, SUAVE, "nodo HL7");
    nodo(3.35, 2.3, 2.9, 1.3, "Catálogo · fila 14", "registro canónico\nde 57 campos", C.accent1, C.background2, "nodo catálogo");
    nodo(6.65, 1.9, 3.15, 1.0, "PostgreSQL · sedes 1 y 3", "usuario.municipio_residencia", C.accent3, T_AZUL, "nodo postgres");
    nodo(6.65, 3.05, 3.15, 1.0, "MongoDB · sede 2", "residencia.municipio_dane", C.accent4, T_VERDE, "nodo mongo");
    nodo(10.2, 2.3, 2.53, 1.3, "FHIR R4", "Patient.address\n.district", C.accent1, C.background2, "nodo fhir");
    flecha(s, 2.95, 2.95, 3.35, 2.95, C.text2, "f1", 2);
    flecha(s, 6.25, 2.95, 6.65, 2.4, C.text2, "f2", 2);
    flecha(s, 6.25, 2.95, 6.65, 3.55, C.text2, "f3", 2);
    flecha(s, 9.8, 2.95, 10.2, 2.95, C.text2, "f4", 2);
    const stats = [
      ["57", "campos en un catálogo", "cada uno con su origen HL7 / CSV y su destino en PostgreSQL, MongoDB y FHIR"],
      ["4", "segmentos Z", "ZPI · ZPV · ZRX · ZEG para lo que HL7 v2.5 no trae"],
      ["56/57", "campos en el mensaje completo", "100 % de los obligatorios; solo falta el 42 (sale vivo)"],
    ];
    stats.forEach(([n, l, d], i) => {
      const x = 0.6 + i * 4.13;
      caja(s, x, 4.55, 3.87, 2.2, SUAVE, null, "dato " + l, 0.1);
      texto(s, n, { x: x + 0.3, y: 4.7, w: 3.3, h: 0.85, fontFace: HEAD, fontSize: 44, bold: true, color: C.accent1, valign: "middle" });
      texto(s, l, { x: x + 0.3, y: 5.55, w: 3.3, h: 0.35, fontSize: 16, bold: true, color: C.text1 });
      texto(s, d, { x: x + 0.3, y: 5.92, w: 3.3, h: 0.75, fontSize: 13, color: MUTED });
    });
    s.addNotes(
      "Presenta B (Sharit).\n" +
      "El corazón del bus es un catálogo único de 57 campos: para cada campo dice de dónde sale en HL7 o CSV, en qué columna queda en PostgreSQL, en qué ruta en MongoDB y en qué elemento de FHIR. " +
      "Ejemplo, campo 14, municipio de residencia: llega en PID-11 componente 9 con el código DANE 70001; el traductor llena el registro canónico; en Cartagena queda en residencia.municipio_dane, en las sedes PostgreSQL en usuario.municipio_residencia, y en FHIR en Patient.address.district. " +
      "Lo que HL7 v2.5 no trae viaja en cuatro segmentos Z que acordamos para el proyecto. Con el mensaje completo cubrimos 56 de 57 campos; solo falta el 42, diagnóstico de muerte, porque el paciente sale vivo.\n\n" +
      "Pregunta probable: ¿cómo maneja el traductor esquemas distintos? Respuesta: ninguna función tiene nombres de columna escritos a mano; a_postgres, a_mongo y sus inversas los toman del catálogo. Hay una prueba de ida y vuelta canónico → Mongo → canónico que conserva los 57."
    );
  }

  // ============================================================ 6. HSB y estados
  {
    const s = contenido("Arquitectura", "El bus: cada mensaje tiene un estado");
    const est = (t, x, y, fill, color, w = 1.9) => pastilla(s, t, x, y, w, 0.58, fill, color, { fontSize: 13, line: { color: color === C.background1 ? fill : color, width: 1.25 } });
    est("RECIBIDO", 0.6, 1.75, C.background2, C.text2);
    est("VALIDADO", 2.85, 1.75, C.background2, C.text2);
    est("TRANSFORMADO", 5.1, 1.75, C.background2, C.text2);
    est("ENTREGADO", 7.35, 1.75, C.accent5, C.background1);
    flecha(s, 2.5, 2.04, 2.85, 2.04, C.text2, "e1"); flecha(s, 4.75, 2.04, 5.1, 2.04, C.text2, "e2"); flecha(s, 7.0, 2.04, 7.35, 2.04, C.text2, "e3");
    est("RECHAZADO", 1.95, 3.35, T_ROJO, C.accent6);
    flecha(s, 2.25, 2.33, 2.25, 3.35, C.accent6, "r1", 1.25); flecha(s, 3.55, 2.33, 3.55, 3.35, C.accent6, "r2", 1.25);
    est("DUPLICADO", 0.6, 4.75, SUAVE, MUTED, 1.5);
    flecha(s, 0.9, 2.33, 0.9, 4.75, MUTED, "d1", 1.25);
    est("REINTENTANDO", 5.1, 3.35, T_AMBAR, C.accent2);
    flecha(s, 6.05, 2.33, 6.05, 3.35, C.accent2, "t1", 1.25);
    flecha(s, 7.0, 3.5, 7.9, 2.33, C.accent5, "t2", 1.25);
    texto(s, "reintento OK", { x: 7.65, y: 2.85, w: 1.4, h: 0.3, fontSize: 12, color: C.accent5, bold: true });
    est("MUERTO", 5.1, 4.75, C.accent6, C.background1);
    flecha(s, 5.6, 3.93, 5.6, 4.75, C.accent6, "m1", 1.25);
    flecha(s, 6.5, 4.75, 6.5, 3.93, C.accent2, "m2", 1.25);
    texto(s, "7 intentos\no error de datos", { x: 3.55, y: 4.0, w: 1.95, h: 0.6, fontSize: 12, color: C.accent6, align: "right" });
    texto(s, "POST /hsb/reencolar", { x: 6.62, y: 4.15, w: 2.4, h: 0.3, fontSize: 12, color: C.accent2, fontFace: MONO, bold: true });
    // esperas
    texto(s, "Esperas entre intentos (segundos), en segundo plano; la petición ya respondió 202", { x: 0.6, y: 5.6, w: 8.6, h: 0.3, fontSize: 13, color: MUTED });
    [2, 4, 8, 16, 32, 64].forEach((n, i) => {
      s.addText(String(n), { shape: pres.shapes.OVAL, x: 0.6 + i * 0.85, y: 6.0, w: 0.62, h: 0.62, fill: { color: C.accent2 }, color: C.background1, bold: true, fontSize: 15, align: "center", valign: "middle", margin: 0, objectName: "espera " + n });
    });
    texto(s, "= 7 intentos", { x: 5.75, y: 6.0, w: 2, h: 0.62, fontSize: 16, bold: true, color: C.accent2, valign: "middle" });
    // notas a la derecha
    const n = [
      ["FaFingerprint", "Idempotencia", "MSH-10 o hash SHA-256 guardado en mensaje_bus de la sede"],
      ["FaRandom", "HAPI, luego la sede", "PUT e UPSERT: repetir los dos pasos es seguro"],
      ["FaBan", "Error de datos: MUERTO", "Un 4xx o un CHECK violado no se reintenta"],
    ];
    n.forEach(([ic, h, d], i) => {
      const y = 1.6 + i * 1.75;
      circuloIcono(s, I[ic], 9.55, y, 0.62, C.accent1, h);
      texto(s, h, { x: 10.35, y: y - 0.02, w: 2.38, h: 0.62, fontSize: 16, bold: true, color: C.text2, valign: "middle" });
      texto(s, d, { x: 10.35, y: y + 0.62, w: 2.38, h: 0.95, fontSize: 14, color: MUTED });
    });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "Cada mensaje recorre estados que quedan guardados en mensaje_bus de su sede: recibido, validado, transformado y entregado. Lo que no cumple las reglas se rechaza con todos sus motivos. " +
      "Antes de validar, el bus busca el MSH-10 o el hash del contenido: si ya lo entregó, responde duplicado sin tocar nada. " +
      "Entrega primero a HAPI y luego a la sede. Si alguno no responde, el mensaje pasa a reintentando: la petición ya respondió 202 y un hilo en segundo plano reintenta con esperas de 2 a 64 segundos, 7 intentos. Si se agotan queda muerto, y se puede reencolar. " +
      "Los errores de datos van directo a muerto, porque el mismo dato fallará igual en el intento 7.\n\n" +
      "Pregunta probable: ¿qué pasa si el bus muere entre «HAPI OK» y «sede OK»? Respuesta: el mensaje quedó en TRANSFORMADO con su contenido original. Al arrancar, recuperar_pendientes() lo relee de las sedes y lo reprograma; el PUT sobrescribe el mismo recurso y la sede hace UPSERT, así que termina ENTREGADO sin duplicados. Lo medimos: recuperó 2 mensajes pendientes."
    );
  }

  // ============================================================ 7. FHIR R4
  {
    const s = contenido("Arquitectura", "FHIR R4: un Bundle por mensaje, sin duplicados");
    const tipos = ["Condition", "Observation", "Organization", "Practitioner", "Encounter", "MedicationRequest", "Patient", "AllergyIntolerance"];
    const vals = [7, 5, 3, 3, 3, 3, 1, 1];
    s.addChart(pres.charts.BAR, [{ name: "Recursos", labels: tipos.slice().reverse(), values: vals.slice().reverse() }], {
      x: 0.6, y: 1.45, w: 6.4, h: 5.35, barDir: "bar", chartColors: [HEX.accent1],
      showTitle: true, title: "Bundle del paciente 1001 · 26 recursos", titleFontSize: 16, titleColor: HEX.dk1, titleFontFace: "+mn-lt",
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 13, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
      catAxisLabelColor: MUTED, catAxisLabelFontSize: 13, catAxisLabelFontFace: "+mn-lt",
      valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
      catAxisLineShow: false, showLegend: false, barGapWidthPct: 45,
    });
    caja(s, 7.4, 1.5, 5.33, 2.2, C.background2, null, "cero errores", 0.12);
    circuloIcono(s, I.FaCheckCircle, 7.7, 1.85, 0.8, C.accent5, "validado");
    texto(s, "0 errores", { x: 8.75, y: 1.7, w: 3.8, h: 0.9, fontFace: HEAD, fontSize: 44, bold: true, color: C.accent5, valign: "middle" });
    texto(s, "al validar el Bundle con $validate en HAPI FHIR (33 advertencias por extensiones propias)", { x: 8.75, y: 2.6, w: 3.8, h: 0.95, fontSize: 14, color: C.text1 });
    caja(s, 7.4, 4.0, 5.33, 1.45, C.text1, null, "ids deterministas", 0.1);
    texto(s, "PUT Patient/pac-1007\nPUT Encounter/enc-V-S2-0101\nPUT Condition/cond-V-S2-0101-ing-J45.9", { x: 7.65, y: 4.15, w: 4.9, h: 1.15, fontFace: MONO, fontSize: 13, color: C.background2, paraSpaceAfter: 6 });
    circuloIcono(s, I.FaFingerprint, 7.4, 5.85, 0.55, C.accent1, "idempotente");
    texto(s, "Ids deterministas: reenviar el mensaje reemplaza el mismo recurso", { x: 8.1, y: 5.78, w: 4.63, h: 0.7, fontSize: 14, color: C.text1, valign: "middle" });
    s.addNotes(
      "Presenta B (Sharit).\n" +
      "Cada mensaje se convierte en un Bundle de tipo transaction. Todas sus entradas usan PUT con identificadores deterministas: Patient/pac más el documento, Encounter/enc más el número de visita, y así. " +
      "Por eso reenviar el mismo mensaje no crea otro paciente: reemplaza el mismo recurso. " +
      "La historia del paciente 1001, armada con atenciones de las tres sedes, da un Bundle de 26 recursos; lo validamos en HAPI con $validate y salió con 0 errores. Las 33 advertencias vienen de extensiones y sistemas de códigos propios que HAPI no puede resolver.\n\n" +
      "Pregunta probable: ¿por qué reenviar un mensaje no crea un paciente duplicado? Respuesta: tres capas, y cualquiera sola basta: el bus reconoce el MSH-10 o el hash en mensaje_bus de la sede; el Bundle usa PUT a ids deterministas; y la sede guarda por la misma llave (ON CONFLICT en PostgreSQL, _id en MongoDB). Medido: 1 solo Patient 1007 y 1 documento en MongoDB tras el reenvío."
    );
  }

  // ============================================================ 8. Seguridad
  pres.addSection({ title: "Seguridad y vistas" });
  {
    const s = contenido("Seguridad y vistas", "Seguridad: permisos en la API, auditoría encadenada");
    const filas = [
      ["FaKey", "JWT en cada petición", "La API valida el token y el rol, no la pantalla"],
      ["FaUserCog", "4 roles + administrador por sede", "Paciente, admisionista, médico y auditor"],
      ["FaBan", "403 auditado", "Cada intento denegado entra a la cadena"],
      ["FaLink", "Cadena SHA-256", "Cada evento firma al anterior; se señala el alterado"],
      ["FaUserPlus", "Cuenta del paciente", "Contraseña temporal y cambio obligatorio"],
    ];
    filas.forEach(([ic, h, d], i) => {
      const y = 1.55 + i * 1.03;
      circuloIcono(s, I[ic], 0.6, y + 0.05, 0.7, i === 3 ? C.accent2 : C.accent1, h);
      texto(s, h, { x: 1.55, y, w: 4.9, h: 0.4, fontSize: 17, bold: true, color: C.text2, valign: "middle" });
      texto(s, d, { x: 1.55, y: y + 0.42, w: 4.9, h: 0.4, fontSize: 14, color: MUTED });
    });
    const hc = altoMarco(S.cuenta, 5.9);
    marco(s, S.cuenta, 6.83, 1.5, 5.9, hc, "Captura: paciente registrado con cuenta y contraseña temporal");
    const w403 = 3.3, h403 = altoMarco(S.denegado, w403);
    marco(s, S.denegado, 8.13, 1.5 + hc + 0.35, w403, h403, "Captura: error 403 acceso denegado");
    s.addNotes(
      "Presenta B (Sharit).\n" +
      "Los permisos se validan en la API, no en la pantalla: cada petición trae un JWT y cada ruta declara qué roles la pueden usar. Hay cuatro roles más el administrador, que puede ser general o de una sola sede. " +
      "Si alguien intenta algo que no le toca, recibe 403 y el intento queda registrado como ACCESO_DENEGADO. " +
      "La auditoría vive en pg_central y es una cadena: cada evento guarda el hash del anterior y su propio hash sobre todos sus campos. " +
      "Y al admitir a un paciente nuevo se le crea su cuenta con una contraseña temporal que se muestra una sola vez; en el primer ingreso debe cambiarla.\n\n" +
      "Pregunta probable: ¿cómo sabe que la auditoría no fue alterada? Respuesta: el verificador recorre la cadena y en cada evento comprueba el índice, el enlace con el anterior y recalcula el hash con los datos actuales. Un UPDATE cambia el contenido pero no puede rehacer el hash sin rehacer toda la cadena; lo detectamos en el índice exacto 3. " +
      "Si piden cambiar un rol en vivo: en app/main.py, vista_reporte, quitar \"paciente\" de requerir_roles, docker compose up -d --build api, y el paciente recibe 403."
    );
  }

  // ============================================================ 9. Vistas
  {
    const s = contenido("Seguridad y vistas", "Cuatro vistas, una por rol");
    const v = [
      [S.paciente, "Paciente · su historia y quién la vio", "FaIdCard"],
      [S.admision, "Admisión · en qué sedes existe", "FaClipboardList"],
      [S.medico, "Médico · escribe con sello", "FaStethoscope"],
      [S.reporte, "Reporte de HC · 3 sedes, cobertura", "FaFileAlt"],
    ];
    const w = 5.92, h = altoMarco(S.paciente, w);
    v.forEach(([img, lab, ic], i) => {
      const x = 0.6 + (i % 2) * (w + 0.29), y = 1.4 + Math.floor(i / 2) * (h + 0.3);
      marco(s, img, x, y, w, h, "Captura vista " + lab);
      s.addText([{ text: lab }], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.2, x: x + 0.18, y: y + h - 0.55, w: 3.6, h: 0.38, fill: { color: C.text2 }, color: C.background1, fontSize: 14, bold: true, align: "center", valign: "middle", margin: 0, shadow: sombra(), objectName: "etiqueta " + lab });
    });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "Estas son las cuatro vistas que pide la guía, cada una con lo que su rol puede ver. " +
      "El paciente ve su historia unificada, ordenada por fecha y con la sede de cada atención, descarga su Bundle y ve quién accedió a su historia. " +
      "La admisionista busca por documento y ve en qué sedes existe el paciente, admite y sigue el estado de sus mensajes en el bus; no ve diagnósticos. " +
      "El médico consulta la historia unificada y registra diagnósticos, órdenes y egresos; cada escritura devuelve un sello, que es el hash del evento de auditoría. " +
      "El Reporte de HC agrupa por sede, muestra la cobertura de los 57 campos, el sello del reporte y la pestaña de estado de la plataforma. Todo esto se ve en vivo en el bloque final de la demo."
    );
  }

  // ============================================================ 10. Panel de administración
  {
    const s = contenido("Seguridad y vistas", "Panel de administración en vivo");
    const hl = 5.3, wl = (hl - 0.14) * S.resumen.w / S.resumen.h + 0.14;
    marco(s, S.resumen, 0.6, 1.45, wl, hl, "Captura: panel de administración, resumen y sedes");
    const xr = 0.6 + wl + 0.4, wr = 12.73 - xr;
    const hu = altoMarco(S.usuarios, wr);
    marco(s, S.usuarios, xr, 1.45, wr, hu, "Captura: gestión de usuarios por sede");
    const notas = [
      ["FaTachometerAlt", "Sedes, FHIR, bus y auditoría", "se actualizan solos cada pocos segundos"],
      ["FaUsers", "Usuarios por sede", "un administrador de sede solo gestiona la suya"],
    ];
    notas.forEach(([ic, h, d], i) => {
      const y = 1.45 + hu + 0.4 + i * 0.95;
      circuloIcono(s, I[ic], xr, y, 0.6, i === 1 ? C.accent2 : C.accent1, h);
      texto(s, h, { x: xr + 0.8, y: y - 0.05, w: wr - 0.8, h: 0.38, fontSize: 16, bold: true, color: C.text2, valign: "middle" });
      texto(s, d, { x: xr + 0.8, y: y + 0.33, w: wr - 0.8, h: 0.35, fontSize: 14, color: MUTED });
    });
    s.addNotes(
      "Presenta B (Sharit).\n" +
      "El administrador tiene un panel que se actualiza solo: sedes activas, estado del servidor FHIR, cobertura FHIR, mensajes recibidos, entregados y rechazados, latencia media del bus y estado de la cadena de auditoría. " +
      "Abajo, cada sede con su motor, su latencia y su cobertura FHIR. " +
      "En la sección de usuarios se crean cuentas por rol y por sede, se desactivan o se restablece la contraseña; un administrador de sede solo ve y crea usuarios de su sede, y el auditor puede consultar pero no gestionar. " +
      "Estas cuentas viven en pg_central, con contraseña PBKDF2, para que apagar una sede no deje a nadie sin poder entrar."
    );
  }

  // ============================================================ 11. Resiliencia
  pres.addSection({ title: "Resultados" });
  {
    const s = contenido("Resultados", "Resiliencia: probada apagando piezas");
    const cw = 3.87, cx = (i) => 0.6 + i * (cw + 0.26);
    const enc = (i, ic, h, col) => {
      caja(s, cx(i), 1.45, cw, 5.35, SUAVE, LINEA, "escenario " + h, 0.1);
      circuloIcono(s, I[ic], cx(i) + 0.25, 1.68, 0.62, col, h);
      texto(s, h, { x: cx(i) + 1.0, y: 1.66, w: cw - 1.15, h: 0.66, fontSize: 17, bold: true, color: C.text2, valign: "middle" });
    };
    // 1: sede mongo caída
    enc(0, "FaPowerOff", "Cae la sede MongoDB", C.accent6);
    const iw = cw - 0.4;
    const h1 = altoMarco(S.sedeCaida, iw), h2 = altoMarco(S.incompleto, iw);
    marco(s, S.sedeCaida, cx(0) + 0.2, 2.55, iw, h1, "Captura: sede 2 caída en el panel");
    marco(s, S.incompleto, cx(0) + 0.2, 2.55 + h1 + 0.2, iw, h2, "Captura: reporte incompleto");
    texto(s, "Responde con 2 sedes y avisa\n/health: DEGRADED · 2/3", { x: cx(0) + 0.25, y: 5.75, w: cw - 0.5, h: 0.8, fontSize: 14, bold: true, color: C.accent6 });
    // 2: HAPI apagado
    enc(1, "FaRedo", "HAPI apagado al enviar", C.accent2);
    texto(s, "132 s", { x: cx(1) + 0.25, y: 2.55, w: cw - 0.5, h: 1.0, fontFace: HEAD, fontSize: 54, bold: true, color: C.accent2 });
    texto(s, "entregado solo, en el intento 7, sin duplicar", { x: cx(1) + 0.25, y: 3.55, w: cw - 0.5, h: 0.7, fontSize: 15, color: C.text1 });
    const dot = 0.36, gap = (cw - 0.5 - 7 * dot) / 6;
    for (let k = 0; k < 7; k++) {
      const x = cx(1) + 0.25 + k * (dot + gap);
      s.addShape(pres.shapes.OVAL, { x, y: 4.65, w: dot, h: dot, fill: { color: k < 6 ? C.accent6 : C.accent5 }, line: { type: "none" }, objectName: "intento " + (k + 1) });
      texto(s, String(k + 1), { x: x - 0.05, y: 5.05, w: dot + 0.1, h: 0.3, fontSize: 12, color: MUTED, align: "center" });
    }
    texto(s, "intentos · esperas de 2 a 64 s", { x: cx(1) + 0.25, y: 5.4, w: cw - 0.5, h: 0.3, fontSize: 12, color: MUTED });
    texto(s, "129,5 s (10 nov.) · 132,0 s (11 nov.)", { x: cx(1) + 0.25, y: 5.85, w: cw - 0.5, h: 0.6, fontSize: 14, bold: true, color: C.text2 });
    // 3: mensaje muerto
    enc(2, "FaInbox", "Mensaje MUERTO", C.text1);
    texto(s, "2,6 s", { x: cx(2) + 0.25, y: 2.55, w: cw - 0.5, h: 1.0, fontFace: HEAD, fontSize: 54, bold: true, color: C.accent5 });
    texto(s, "para entregarlo tras reencolar, en 1 intento", { x: cx(2) + 0.25, y: 3.55, w: cw - 0.5, h: 0.7, fontSize: 15, color: C.text1 });
    pastilla(s, "MUERTO", cx(2) + 0.25, 4.55, 1.3, 0.48, C.accent6, C.background1, { fontSize: 13 });
    flecha(s, cx(2) + 1.6, 4.79, cx(2) + 2.2, 4.79, C.text2, "reencolar", 2);
    pastilla(s, "ENTREGADO", cx(2) + 2.25, 4.55, 1.37, 0.48, C.accent5, C.background1, { fontSize: 13 });
    texto(s, "POST /hsb/reencolar/{id}", { x: cx(2) + 0.25, y: 5.2, w: cw - 0.5, h: 0.35, fontFace: MONO, fontSize: 12, bold: true, color: C.text2 });
    texto(s, "Superó 7 intentos con HAPI apagado; al volver HAPI se reencoló", { x: cx(2) + 0.25, y: 5.75, w: cw - 0.5, h: 0.8, fontSize: 14, color: MUTED });
    s.addNotes(
      "Presenta B (Sharit). Corresponde a los bloques 5, 6 y 7 de la demo.\n" +
      "Probamos la resiliencia apagando piezas de verdad. Primero, docker stop mongo_sede2: la consulta del paciente 1001 responde con Sincelejo y Corozal, marca el reporte como incompleto y /health pasa a DEGRADED con 2 de 3 nodos; al encender el contenedor vuelve Cartagena. " +
      "Segundo, con HAPI apagado enviamos un mensaje: el bus responde reintentando, sigue intentando con esperas crecientes y lo entregó solo en el intento 7, a los 132 segundos, sin duplicar. " +
      "Tercero, si HAPI tarda más que la ventana de reintentos el mensaje queda MUERTO; con HAPI de nuevo arriba, POST /hsb/reencolar lo entregó en 2,6 segundos.\n\n" +
      "Pregunta probable: ¿por qué los errores de datos no se reintentan? Respuesta: reintentar sirve para fallas transitorias. Un CHECK violado o un 4xx de HAPI fallará igual en el intento 7; solo gastaría dos minutos de cola. Esos se marcan como permanentes y van directo a MUERTO con su motivo."
    );
  }

  // ============================================================ 12. Resultados medidos
  {
    const s = contenido("Resultados", "Resultados medidos");
    const tiles = [
      ["FaCheckCircle", "0", "errores FHIR", "$validate · Bundle de 26 recursos", C.accent5],
      ["FaClipboardList", "56/57", "campos · mensaje completo", "100 % de los obligatorios", C.accent1],
      ["FaLayerGroup", "52/57", "campos · paciente 1001", "3 sedes, 2 motores, 100 % obligatorios", C.accent1],
      ["FaClone", "1", "Patient 1007 tras reenviar", "el bus respondió «duplicado»", C.accent1],
      ["FaUndo", "ROLLBACK", "ACID en PostgreSQL", "CHECK violado: sin usuario huérfano", C.accent3],
      ["FaVial", "44/44", "pruebas automatizadas", "pytest, en 8,78 s", C.accent5],
      ["FaExchangeAlt", "148", "mensajes de prueba", "135 entregados · 8 rechazados · 5 duplicados", C.accent1],
      ["FaLink", "Índice 3", "auditoría alterada", "detectada por el verificador de la cadena", C.accent2],
    ];
    const w = 2.86, h = 2.5, gx = (12.13 - 4 * w) / 3;
    tiles.forEach(([ic, n, l, d, col], i) => {
      const x = 0.6 + (i % 4) * (w + gx), y = 1.45 + Math.floor(i / 4) * (h + 0.3);
      caja(s, x, y, w, h, SUAVE, LINEA, "resultado " + l, 0.1);
      circuloIcono(s, I[ic], x + 0.25, y + 0.25, 0.5, col, l);
      const largo = n.length > 5;
      texto(s, n, { x: x + 0.25, y: y + 0.8, w: w - 0.4, h: 0.75, fontFace: HEAD, fontSize: largo ? 30 : 40, bold: true, color: col, valign: "middle" });
      texto(s, l, { x: x + 0.25, y: y + 1.55, w: w - 0.4, h: 0.35, fontSize: 15, bold: true, color: C.text1 });
      texto(s, d, { x: x + 0.25, y: y + 1.9, w: w - 0.4, h: 0.55, fontSize: 12, color: MUTED });
    });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "Estos números son medidos en Kali Linux, en una máquina virtual de 3,8 GB con Docker 28, el 10 y 11 de noviembre. " +
      "El Bundle del paciente 1001 validó con 0 errores. El mensaje completo cubre 56 de 57 campos y la historia real de 1001, desde tres sedes y dos motores, 52 de 57, siempre con el 100 % de los obligatorios. " +
      "Reenviar el ejemplo 01 dejó un solo Patient 1007. La demo de ACID en PostgreSQL hace rollback completo cuando se viola un CHECK. Pasan las 44 pruebas automatizadas. " +
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
      ["00:00", "A", "Arranque limpio desde cero", "docker compose down -v && docker compose up -d --build"],
      ["02:00", "B", "Cobertura FHIR en 0 %", "localhost:8000/reporte?pestana=tablero"],
      ["03:00", "A", "HL7 y CSV entran; sube la cobertura", "POST /hsb/hl7  ·  POST /hsb/csv?sede=3"],
      ["05:30", "B", "Reenvío: el bus responde duplicado", "ejemplo 01 otra vez → \"duplicado\""],
      ["07:30", "B", "Cae la sede MongoDB y se recupera", "docker stop mongo_sede2  ·  docker start"],
      ["10:30", "B", "Auditoría alterada y detectada", "UPDATE evento_auditoria … WHERE indice = 3"],
      ["12:00", "A+B", "Consulta unificada y Reporte de HC", "localhost:8000/reporte?buscar_doc=1001"],
    ];
    const y0 = 1.45, rh = 0.71;
    s.addShape(pres.shapes.LINE, { x: 0.84, y: y0 + 0.24, w: 0, h: rh * 6, line: { color: LINEA, width: 2 }, objectName: "línea de tiempo" });
    pasos.forEach(([min, quien, t, cmd], i) => {
      const y = y0 + i * rh;
      s.addText(String(i + 1), { shape: pres.shapes.OVAL, x: 0.6, y, w: 0.48, h: 0.48, fill: { color: C.accent1 }, color: C.background1, bold: true, fontSize: 15, align: "center", valign: "middle", margin: 0, objectName: "paso " + (i + 1) });
      texto(s, min, { x: 1.3, y, w: 0.85, h: 0.48, fontSize: 14, color: MUTED, valign: "middle", bold: true });
      pastilla(s, quien, 2.2, y + 0.04, 0.68, 0.4, quien === "B" ? C.text1 : C.accent1, C.background1, { fontSize: 13 });
      texto(s, t, { x: 3.1, y, w: 3.95, h: 0.48, fontSize: 16, bold: true, color: C.text1, valign: "middle" });
      texto(s, cmd, { x: 7.05, y, w: 5.68, h: 0.48, fontFace: MONO, fontSize: 12, color: C.text2, valign: "middle", fill: { color: C.background2 }, margin: 4 });
    });
    texto(s, "Intercalado (A): mensaje de 57 campos con HAPI apagado a las 06:30; se ve entregado a las 09:30 (56/57 campos).", { x: 0.6, y: 6.5, w: 12.13, h: 0.35, fontSize: 13, color: MUTED, italic: true });
    s.addNotes(
      "Presentan A y B. Esta diapositiva queda de fondo como mapa de la demo.\n" +
      "Seguimos el orden de la guía de la Fase 5. A arranca desde cero con docker compose down -v y up -d --build. B entra como auditor_elena y muestra el tablero con la cobertura FHIR en 0 %. " +
      "A envía los ejemplos 01 a 04 (dos HL7 válidos, uno inválido con 3 motivos y el CSV con 3 entregados y 2 rechazados) y la cobertura sube: sede 1 50 %, sede 2 33,3 %, sede 3 75 %. " +
      "B reenvía el ejemplo 01 y el bus responde duplicado; hay un solo Patient 1007 en HAPI y un solo documento en MongoDB. " +
      "A apaga HAPI y envía el mensaje de 57 campos: queda reintentando. B detiene mongo_sede2 y muestra el reporte incompleto y DEGRADED; luego la recupera. A muestra que el mensaje de 57 campos se entregó solo. " +
      "B hace el 403 como paciente y el UPDATE en pg_central; el tablero marca el índice 3. Cierre: A con el Reporte de HC de 1001 y B con una escritura del médico que devuelve su sello.\n" +
      "Si algo falla: si el mensaje de 57 campos queda MUERTO, curl -X POST localhost:8001/hsb/reencolar/MSG-0057; si el ejemplo 01 sale duplicado la primera vez, faltó el down -v."
    );
  }

  // ============================================================ 14. Limitaciones
  {
    const s = contenido("Demo y cierre", "Limitaciones y trabajo futuro");
    texto(s, "Hoy", { x: 0.6, y: 1.4, w: 5.5, h: 0.4, fontSize: 16, bold: true, color: C.accent2 });
    texto(s, "Siguiente paso", { x: 7.0, y: 1.4, w: 5.5, h: 0.4, fontSize: 16, bold: true, color: C.accent1 });
    const filas = [
      ["MongoDB sin replica set", "Replica set y versión del documento"],
      ["HSB (:8001) sin autenticación", "Keycloak / OIDC y TLS entre servicios"],
      ["Una sola instancia de HAPI FHIR", "Varias instancias sobre PostgreSQL"],
      ["Latencia no medida con carga", "Prueba de carga: latencia, mensajes/min, % fallidos"],
      ["Kubernetes sin probar en Minikube", "Correr infra/k8s en Minikube y CI con las 44 pruebas"],
    ];
    filas.forEach(([a, b], i) => {
      const y = 1.9 + i * 0.97;
      caja(s, 0.6, y, 5.7, 0.78, T_AMBAR, null, "limitación " + a, 0.08);
      s.addImage({ data: IA.FaExclamationTriangle, x: 0.85, y: y + 0.22, w: 0.34, h: 0.34, altText: "limitación", objectName: "icono limitación " + (i + 1) });
      texto(s, a, { x: 1.4, y, w: 4.8, h: 0.78, fontSize: 16, color: C.text1, valign: "middle" });
      flecha(s, 6.4, y + 0.39, 6.9, y + 0.39, C.text2, "flecha " + (i + 1), 2);
      caja(s, 7.0, y, 5.73, 0.78, C.background2, null, "futuro " + b, 0.08);
      circuloIcono(s, I.FaCheckCircle, 7.2, y + 0.17, 0.44, C.accent1, "futuro " + (i + 1));
      texto(s, b, { x: 7.8, y, w: 4.85, h: 0.78, fontSize: 16, color: C.text1, valign: "middle" });
    });
    s.addNotes(
      "Presenta A (Jose).\n" +
      "Queremos ser honestos con lo que el prototipo no resuelve. MongoDB corre sin replica set: no hay conmutación por fallo ni transacciones multi-documento. " +
      "Los endpoints del HSB en el 8001 no exigen autenticación; solo la API la exige. Hay una sola instancia de HAPI. No medimos latencia ni mensajes por minuto con una prueba de carga. " +
      "Y aunque dejamos manifiestos de Kubernetes para Minikube, no presentamos evidencia de que corran. " +
      "El trabajo futuro sale directo de esa lista: replica set, Keycloak con TLS, HAPI sobre PostgreSQL con varias instancias, una prueba de carga y un pipeline de CI que corra las 44 pruebas.\n\n" +
      "Pregunta probable: ¿qué pasa si alguien con acceso a pg_central rehace toda la cadena? Respuesta: puede hacerlo; por eso el trabajo futuro incluye anclar periódicamente el último hash fuera del sistema, por ejemplo en Hyperledger Fabric."
    );
  }

  // ============================================================ 15. Cierre
  {
    const s = pres.addSlide({ masterName: "PORTADA", sectionTitle: "Demo y cierre" });
    s.addImage({ data: LOGO, x: 0.8, y: 0.75, w: 0.75, h: 0.75, altText: "Logo de la plataforma", objectName: "logo" });
    s.addText("Gracias", { placeholder: "title" });
    s.addText("¿Preguntas?", { placeholder: "body" });
    const filas = [
      ["FaDesktop", "Demo en vivo", "http://192.168.1.94:8000"],
      ["FaGithub", "Repositorio · etiqueta v1.0", "github.com/jose18000/Parcial-Final-Sistemas-Distribuidos-Plataforma-de-Interoperabilidad-en-Salud"],
    ];
    filas.forEach(([ic, h, d], i) => {
      const y = 5.0 + i * 0.95;
      circuloIcono(s, I[ic], 0.8, y, 0.6, C.accent1, h);
      texto(s, h, { x: 1.6, y: y - 0.05, w: 7.0, h: 0.32, fontSize: 14, bold: true, color: C.background2 });
      texto(s, d, { x: 1.6, y: y + 0.28, w: 7.0, h: 0.55, fontSize: 14, color: C.background1, fontFace: i === 0 ? MONO : undefined, bold: i === 0 });
    });
    s.addNotes(
      "Presenta B (Sharit).\n" +
      "Para cerrar: un catálogo de 57 campos, un registro canónico y entregas idempotentes bastaron para unificar tres sedes con motores distintos, sin transacción distribuida y sin tocar los sistemas legados. " +
      "La demo está corriendo en http://192.168.1.94:8000 y el código está en el repositorio con la etiqueta v1.0; el README tiene todos los pasos y los usuarios de prueba. " +
      "Gracias. Quedamos atentos a sus preguntas; las respondemos los dos.\n\n" +
      "Reparto de preguntas (para no pisarse): A lidera CAP con la sede caída, auditoría, escalar 100×, bus caído entre HAPI y sede, errores de datos. B lidera duplicados, cambio de rol en vivo, por qué MongoDB, viaje de un campo y cobertura."
    );
  }

  await pres.writeFile({ fileName: SALIDA });
  await aplicarTema(SALIDA, THEME);
  console.log("Escrito:", SALIDA);
}

// Escribe los colores del tema en ppt/theme/theme1.xml (pptxgenjs deja la paleta de Office).
async function aplicarTema(archivo, tema) {
  const posibles = [process.env.PPTX_APPLY_THEME].filter(Boolean);
  for (const p of posibles) {
    if (fs.existsSync(p)) { await require(p).applyTheme(archivo, tema); return; }
  }
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
