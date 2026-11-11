/* Historia Clínica Electrónica · Panel de administración en vivo.
   Sin este archivo el panel se ve completo (render del servidor, secciones apiladas); con él:
   - muestra una sección a la vez (#resumen, #pacientes, #usuarios, #integracion, #fhir, #auditoria);
   - consulta /api/panel/resumen cada 5 s, /api/panel/pacientes cada 10 s y /api/panel/usuarios cada 15 s
     (solo con la sección Usuarios visible), sin solapar peticiones (15 s tras un error),
     con pausa/reanudar y botón «Actualizar»;
   - gestiona usuarios (alta, activar/desactivar, restablecer contraseña);
   - anima los cambios de cifras y resalta lo que cambió;
   - busca pacientes (300 ms de espera) y registra pacientes por JSON contra el bus.
   Todo dato del servidor se inserta con textContent / createElement (nunca innerHTML). */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  if (!$("kpis")) return;

  var cfg = {};
  try { cfg = JSON.parse(($("panel-config") || {}).textContent || "{}") || {}; } catch (e) { cfg = {}; }
  var SEDES = cfg.sedes || {};
  var SEXO = cfg.sexo || {};
  var UNIDAD = cfg.unidad_edad || {};
  var ETQ_BUS = cfg.etq_bus || {};
  var ROLES = cfg.roles || {};
  var ORIGENES = cfg.origenes || {};
  var YO = cfg.yo || "";
  var ALCANCE = cfg.alcance || {};
  var reducido = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  var ESTADOS = ["RECIBIDO", "VALIDADO", "TRANSFORMADO", "ENTREGADO", "REINTENTANDO", "DUPLICADO", "RECHAZADO", "MUERTO"];
  var RECURSOS = ["Patient", "Encounter", "Condition", "Observation", "MedicationRequest", "AllergyIntolerance", "Practitioner", "Organization"];

  /* 1. Utilidades ---------------------------------------------------------- */
  function esNum(v) { return typeof v === "number" && isFinite(v); }
  function num(v) { return esNum(v) ? v : 0; }
  function fmt(v) {
    if (!esNum(v)) return "—";
    var neg = v < 0; v = Math.abs(v);
    var s = Number.isInteger(v) ? String(v) : v.toFixed(1);
    var p = s.split(".");
    p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return (neg ? "-" : "") + p.join(",");
  }
  function fecha(f) { return f ? String(f).slice(0, 16).replace("T", " ") : "—"; }
  function txt(v, defecto) { return v === null || v === undefined || v === "" ? (defecto === undefined ? "—" : defecto) : String(v); }

  function el(tag, attrs, hijos) {
    var n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "class") n.className = v;
        else if (k === "text") n.textContent = v;
        else n.setAttribute(k, v === true ? "" : String(v));
      });
    }
    (hijos || []).forEach(function (h) {
      if (h === null || h === undefined || h === false) return;
      n.appendChild(typeof h === "string" || typeof h === "number" ? document.createTextNode(String(h)) : h);
    });
    return n;
  }
  function vaciar(n) { while (n.firstChild) n.removeChild(n.firstChild); }

  var SVG = "http://www.w3.org/2000/svg";
  var ICOS = {
    db: [["ellipse", { cx: 12, cy: 5, rx: 8, ry: 3 }], ["path", { d: "M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" }]],
    hoja: [["path", { d: "M12 2c4 4 6 8 5 12-1 3-3 5-5 6-2-1-4-3-5-6-1-4 1-8 5-12zM12 7v15" }]],
    check: [["path", { d: "M20 6 9 17l-5-5" }]],
    alerta: [["path", { d: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" }]],
    x: [["path", { d: "M18 6 6 18M6 6l12 12" }]],
    info: [["circle", { cx: 12, cy: 12, r: 10 }], ["path", { d: "M12 16v-4M12 8h.01" }]],
    "escudo-ok": [["path", { d: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" }], ["path", { d: "m9 12 2 2 4-4" }]],
    candado: [["rect", { x: 3, y: 11, width: 18, height: 11, rx: 2 }], ["path", { d: "M7 11V7a5 5 0 0 1 10 0v4" }]],
    pausa: [["rect", { x: 6, y: 4, width: 4, height: 16, rx: 1 }], ["rect", { x: 14, y: 4, width: 4, height: 16, rx: 1 }]],
    play: [["path", { d: "m6 4 14 8-14 8z" }]],
    girar: [["path", { d: "M21 12a9 9 0 1 1-2.6-6.4L21 8M21 3v5h-5" }]],
    enviar: [["path", { d: "m22 2-7 20-4-9-9-4zM22 2 11 13" }]],
    usuario: [["path", { d: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" }], ["circle", { cx: 12, cy: 7, r: 4 }]],
    mas: [["path", { d: "M12 5v14M5 12h14" }]],
    reloj: [["circle", { cx: 12, cy: 12, r: 10 }], ["path", { d: "M12 6v6l4 2" }]]
  };
  function ico(nombre, cls) {
    var s = document.createElementNS(SVG, "svg");
    s.setAttribute("class", "ico" + (cls ? " " + cls : ""));
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("focusable", "false");
    (ICOS[nombre] || []).forEach(function (f) {
      var e = document.createElementNS(SVG, f[0]);
      Object.keys(f[1]).forEach(function (k) { e.setAttribute(k, f[1][k]); });
      s.appendChild(e);
    });
    return s;
  }

  function motorNombre(m) { return m === "mongodb" ? "MongoDB" : (m === "postgresql" ? "PostgreSQL" : txt(m, "motor —")); }
  function badgeMotor(m) {
    if (m === "mongodb") return el("span", { class: "badge b-mongo" }, [ico("hoja"), "MongoDB"]);
    if (m === "postgresql") return el("span", { class: "badge b-pg" }, [ico("db"), "PostgreSQL"]);
    return el("span", { class: "badge b-neutro", text: txt(m, "motor —") });
  }
  function badgeEstado(e) {
    var eu = txt(e, "").toUpperCase();
    return el("span", { class: "badge punto " + (ESTADOS.indexOf(eu) >= 0 ? "est-" + eu.toLowerCase() : "b-neutro"), text: eu || "—" });
  }
  function badgeResultado(r) {
    var ru = txt(r, "").toUpperCase();
    var cls = ["EXITOSO", "OK", "EXITO", "ÉXITO", "PERMITIDO"].indexOf(ru) >= 0 ? "b-ok"
      : (["FALLIDO", "DENEGADO", "ERROR", "RECHAZADO"].indexOf(ru) >= 0 ? "b-err" : "b-neutro");
    return el("span", { class: "badge " + cls, text: ru || "—" });
  }
  function badgeUpDown(up) { return el("span", { class: "badge punto " + (up ? "b-ok" : "b-err"), text: up ? "UP" : "DOWN" }); }
  function hashCorto(h) {
    if (!h) return document.createTextNode("—");
    return el("code", { class: "hash-corto", title: String(h), text: String(h).slice(0, 10) + "…" });
  }
  function sedeTxt(s) {
    if (esNum(s)) {
      var d = SEDES[String(s)];
      return "Sede " + s + (d ? " · " + (d.ciudad || d.nombre || "") : "");
    }
    return txt(s);
  }
  function barra(valor, etiqueta) {
    var v = esNum(valor) ? Math.max(0, Math.min(100, valor)) : 0;
    v = Math.round(v * 10) / 10;
    var b = el("div", { class: "barra" + (v < 50 ? " baja" : ""), role: "progressbar", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": v, "aria-label": etiqueta });
    var s = el("span"); s.style.width = v + "%";
    b.appendChild(s);
    return b;
  }

  function copiar(texto) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(texto);
    return new Promise(function (ok, falla) {
      var t = document.createElement("textarea");
      t.value = texto; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
      document.body.appendChild(t); t.select();
      try { if (document.execCommand("copy")) ok(); else falla(); } catch (e) { falla(e); }
      document.body.removeChild(t);
    });
  }
  function chipSello(h, etq, icono) {
    if (!h) return document.createTextNode("—");
    var valor = String(h);
    etq = etq || "código de verificación";
    var chip = el("span", { class: "sello-chip", "data-copiar-js": "" }, [ico(icono || "candado"), el("code", { text: valor })]);
    var b = el("button", { type: "button", class: "btn-copiar", "aria-label": "Copiar " + etq + (valor.length > 16 ? " " + valor.slice(0, 12) + "…" : ""), text: "Copiar" });
    b.addEventListener("click", function () {
      copiar(valor).then(function () {
        b.textContent = "Copiado ✓"; b.classList.add("hecho");
        setTimeout(function () { b.textContent = "Copiar"; b.classList.remove("hecho"); }, 1800);
      }, function () { b.textContent = "Selecciónelo"; });
    });
    chip.appendChild(b);
    return chip;
  }

  /* Anuncios para lectores de pantalla: solo resultados y errores, nunca cada sondeo. */
  var anuncioT = null, anuncioCola = [];
  function anunciar(msg) {
    var a = $("anuncio"); if (!a || !msg) return;
    if (anuncioCola.indexOf(msg) < 0) anuncioCola.push(msg); // mensajes del mismo instante se leen juntos
    clearTimeout(anuncioT);
    a.textContent = "";
    anuncioT = setTimeout(function () { a.textContent = anuncioCola.join(" "); anuncioCola = []; }, 80);
  }

  function destellar(n) {
    if (!n) return;
    n.classList.remove("cambio");
    void n.offsetWidth;
    n.classList.add("cambio");
    clearTimeout(n._destello);
    n._destello = setTimeout(function () { n.classList.remove("cambio"); }, 1500);
  }

  function animarNumero(sp, de, a) {
    if (sp._raf) cancelAnimationFrame(sp._raf);
    if (a === null || de === null || reducido || document.hidden) { sp.textContent = fmt(a); return; }
    var dec = !Number.isInteger(a) || !Number.isInteger(de);
    var t0 = null, dur = 700;
    function paso(t) {
      if (t0 === null) t0 = t;
      var p = Math.min(1, (t - t0) / dur);
      var e = 1 - Math.pow(1 - p, 3);
      var v = de + (a - de) * e;
      sp.textContent = fmt(p < 1 ? (dec ? Math.round(v * 10) / 10 : Math.round(v)) : a);
      if (p < 1) sp._raf = requestAnimationFrame(paso); else sp._raf = null;
    }
    sp._raf = requestAnimationFrame(paso);
  }

  /* 2. Red ----------------------------------------------------------------- */
  function ErrorSesion() { var e = new Error("Sesión expirada"); e.sesion = true; return e; }
  function pedir(url, opciones) {
    var ctrl = window.AbortController ? new AbortController() : null;
    var reloj = ctrl ? setTimeout(function () { ctrl.abort(); }, 10000) : null;
    var op = { credentials: "same-origin", headers: { Accept: "application/json" }, cache: "no-store" };
    if (ctrl) op.signal = ctrl.signal;
    var permitir403 = false;
    Object.keys(opciones || {}).forEach(function (k) { if (k === "permitir403") permitir403 = !!opciones[k]; else op[k] = opciones[k]; });
    return fetch(url, op).then(function (r) {
      clearTimeout(reloj);
      if (r.status === 401 || (r.status === 403 && !permitir403)) throw ErrorSesion();
      if (r.redirected && /\/login(\b|\/|\?|$)/.test(r.url)) throw ErrorSesion();
      return r.text().then(function (t) {
        var datos = null;
        try { datos = t ? JSON.parse(t) : null; } catch (e) { datos = null; }
        return { status: r.status, ok: r.ok, datos: datos };
      });
    }, function (err) {
      clearTimeout(reloj);
      var e = new Error(err && err.name === "AbortError" ? "tiempo de espera agotado" : "sin conexión con el servidor");
      throw e;
    });
  }

  /* 3. Sondeo -------------------------------------------------------------- */
  var NORMAL_ERROR = 15000;
  var q = "";
  var pausado = false, expirada = false;
  var fuentes = {
    resumen: { nombre: "el resumen", cada: 5000, url: function () { return "/api/panel/resumen"; } },
    pacientes: {
      nombre: "la lista de pacientes", cada: 10000,
      url: function () { return "/api/panel/pacientes?limite=50" + (q ? "&q=" + encodeURIComponent(q) : ""); }
    },
    usuarios: {
      nombre: "la lista de usuarios", cada: 15000, soloVisible: "usuarios", permitir403: true,
      url: function () {
        var p = [];
        Object.keys(filtroU).forEach(function (k) { if (filtroU[k]) p.push(k + "=" + encodeURIComponent(filtroU[k])); });
        return "/api/panel/usuarios" + (p.length ? "?" + p.join("&") : "");
      }
    }
  };
  var filtroU = { q: "", rol: "", sede: "" };
  var RENDER = { resumen: function (d) { renderResumen(d); }, pacientes: function (d) { renderPacientes(d); }, usuarios: function (d) { renderUsuarios(d); } };
  var seccionActual = null;
  function hayErrores() { return Object.keys(fuentes).some(function (k) { return fuentes[k].errores; }); }
  function activa(clave) { var f = fuentes[clave]; return !f.soloVisible || !seccionActual || seccionActual === f.soloVisible; }
  Object.keys(fuentes).forEach(function (k) {
    var f = fuentes[k];
    f.timer = null; f.enCurso = false; f.repetir = false; f.errores = 0; f.ultimoOk = Date.now(); f.promesa = null;
  });

  function programar(clave) {
    var f = fuentes[clave];
    clearTimeout(f.timer); f.timer = null;
    if (pausado || expirada || !activa(clave)) return;
    f.timer = setTimeout(function () {
      if (document.hidden) { programar(clave); return; }
      ejecutar(clave);
    }, f.errores ? NORMAL_ERROR : f.cada);
  }

  function ejecutar(clave) {
    var f = fuentes[clave];
    if (expirada) return Promise.resolve();
    clearTimeout(f.timer); f.timer = null;
    if (f.enCurso) { f.repetir = true; return f.promesa; }
    f.enCurso = true;
    var url = f.url();
    f.promesa = pedir(url, f.permitir403 ? { permitir403: true } : null).then(function (r) {
      if (!r.ok || !r.datos || typeof r.datos !== "object") throw new Error("respuesta HTTP " + r.status);
      f.errores = 0; f.ultimoOk = Date.now();
      if (url === f.url()) RENDER[clave](r.datos);
      recuperado();
    }).catch(function (e) {
      if (e && e.sesion) { expirar(); return; }
      f.errores += 1;
      fallo(f, e);
    }).then(function () {
      f.enCurso = false;
      if (expirada) return;
      if (f.repetir) { f.repetir = false; return ejecutar(clave); }
      programar(clave);
    });
    return f.promesa;
  }

  var enError = false;
  function fallo(f, e) {
    var aviso = $("aviso-red"), t = $("aviso-red-texto");
    if (t) t.textContent = "No se pudo actualizar " + f.nombre + " (" + ((e && e.message) || "error") + "). Se reintentará cada 15 s; los datos mostrados pueden estar desactualizados.";
    if (aviso) aviso.hidden = false;
    if (!enError) { enError = true; anunciar("Aviso: no se pudo actualizar el panel. Se reintentará en 15 segundos."); }
    pintarVivo();
  }
  function recuperado() {
    if (hayErrores()) return;
    var aviso = $("aviso-red"); if (aviso) aviso.hidden = true;
    if (enError) { enError = false; anunciar("Conexión restablecida; el panel vuelve a actualizarse."); }
    pintarVivo();
  }
  function expirar() {
    if (expirada) return;
    expirada = true;
    Object.keys(fuentes).forEach(function (k) { clearTimeout(fuentes[k].timer); fuentes[k].timer = null; });
    var s = $("aviso-sesion"); if (s) s.hidden = false;
    var r = $("aviso-red"); if (r) r.hidden = true;
    var b = $("btn-registrar"); if (b) b.disabled = true;
    var bu = $("btn-crear-usuario"); if (bu) bu.disabled = true;
    var p = $("btn-pausa"); if (p) p.disabled = true;
    pintarVivo();
  }

  /* Indicador «En vivo · actualizado hace N s» */
  function hace(ms) {
    var s = Math.max(0, Math.round(ms / 1000));
    if (s < 60) return s + " s";
    var m = Math.floor(s / 60);
    return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + (m % 60) + " min";
  }
  function pintarVivo() {
    var v = $("vivo"), t = $("vivo-texto"); if (!v || !t) return;
    var dt = Date.now() - fuentes.resumen.ultimoOk;
    var cls = "", texto;
    if (expirada) { cls = "expirada"; texto = "Sesión expirada · sin actualizar"; }
    else if (pausado) { cls = "pausado"; texto = "En pausa · actualizado hace " + hace(dt); }
    else if (hayErrores()) { cls = "error"; texto = "Reintentando · último dato hace " + hace(dt); }
    else texto = "En vivo · actualizado hace " + hace(dt);
    v.className = "vivo" + (cls ? " " + cls : "");
    if (t.textContent !== texto) t.textContent = texto;
  }

  function actualizarTodo() {
    return Promise.all(Object.keys(fuentes).filter(activa).map(ejecutar));
  }

  /* 4. Render del resumen -------------------------------------------------- */
  var firmas = {};
  function siCambia(clave, datos, fn) {
    var s;
    try { s = JSON.stringify(datos === undefined ? null : datos); } catch (e) { s = String(Math.random()); }
    if (firmas[clave] === s) return;
    firmas[clave] = s;
    fn(datos);
  }

  function renderResumen(d) {
    var k = d.kpis || {};
    actualizarKpis(k, d);
    siCambia("sedes", d.sedes, renderSedes);
    siCambia("bus", d.bus, renderBus);
    siCambia("fhir", d.fhir, renderFhir);
    siCambia("mensajes", d.mensajes, renderMensajes);
    siCambia("auditoria", d.auditoria, renderAuditoria);
    var g = $("generado-en");
    if (g && d.generado_en) { g.textContent = fecha(d.generado_en); g.setAttribute("datetime", String(d.generado_en)); }
  }

  function tile(nombre) { return document.querySelector('[data-tile="' + nombre + '"]'); }
  function estadoTile(nombre, estado, cambiadas) {
    var t = tile(nombre); if (!t) return;
    var antes = ["ok", "down", "warn"].filter(function (c) { return t.classList.contains(c); })[0] || "";
    ["ok", "down", "warn"].forEach(function (c) { t.classList.toggle(c, c === estado); });
    if (antes !== (estado || "")) cambiadas.push(t);
  }
  function badgeTexto(id, texto, cls, cambiadas) {
    var b = $(id); if (!b) return;
    if (b.textContent !== texto) { b.textContent = texto; var t = b.closest(".kpi"); if (t) cambiadas.push(t); }
    b.className = cls;
  }

  function actualizarKpis(k, d) {
    var kv = {};
    Object.keys(k).forEach(function (c) { kv[c] = k[c]; });
    kv.rechazados_muertos = (esNum(k.mensajes_rechazados) || esNum(k.mensajes_muertos)) ? num(k.mensajes_rechazados) + num(k.mensajes_muertos) : null;
    var cambiadas = [];
    Array.prototype.forEach.call(document.querySelectorAll("[data-k]"), function (sp) {
      var nuevo = kv[sp.getAttribute("data-k")];
      nuevo = esNum(nuevo) ? nuevo : null;
      var vt = sp.getAttribute("data-valor");
      var viejo = vt === "" || vt === null ? null : parseFloat(vt);
      if (nuevo === viejo || (nuevo !== null && viejo !== null && Math.abs(nuevo - viejo) < 1e-9)) return;
      sp.setAttribute("data-valor", nuevo === null ? "" : String(nuevo));
      animarNumero(sp, viejo, nuevo);
      var t = sp.closest(".kpi"); if (t) cambiadas.push(t);
    });

    estadoTile("sedes", esNum(k.sedes_activas) && k.sedes_activas === k.sedes_total ? "ok" : "down", cambiadas);
    var up = k.hapi === "UP";
    estadoTile("hapi", up ? "ok" : "down", cambiadas);
    badgeTexto("k-hapi", up ? "UP" : (k.hapi ? "DOWN" : "—"), "badge badge-lg punto " + (up ? "b-ok" : (k.hapi ? "b-err" : "b-neutro")), cambiadas);

    var cb = $("k-cob-barra");
    if (cb) {
      var v = esNum(k.cobertura_fhir_global) ? Math.max(0, Math.min(100, k.cobertura_fhir_global)) : 0;
      v = Math.round(v * 10) / 10;
      cb.setAttribute("aria-valuenow", v);
      cb.classList.toggle("baja", v < 50);
      if (cb.firstElementChild) cb.firstElementChild.style.width = v + "%";
    }
    var rech = num(k.mensajes_rechazados) + num(k.mensajes_muertos);
    estadoTile("rechazados", num(k.mensajes_muertos) > 0 ? "down" : (rech > 0 ? "warn" : "ok"), cambiadas);
    var fall = num(k.porcentaje_fallidos);
    estadoTile("fallidos", fall >= 20 ? "down" : (fall > 0 ? "warn" : "ok"), cambiadas);
    var integra = k.auditoria_integra;
    estadoTile("auditoria", integra === true ? "ok" : (integra === false ? "down" : ""), cambiadas);
    badgeTexto("k-integra", integra === true ? "Cadena ÍNTEGRA" : (integra === false ? "Cadena ALTERADA" : "Verificador no disponible"),
      "badge " + (integra === true ? "b-ok" : (integra === false ? "b-err" : "b-neutro")), cambiadas);
    var be = $("k-bus-estado");
    if (be) { var nt = txt((d.bus || {}).estado_general); if (be.textContent !== nt) { be.textContent = nt; cambiadas.push(be.closest(".kpi")); } }

    cambiadas.filter(function (t, i) { return t && cambiadas.indexOf(t) === i; }).forEach(destellar);
  }

  function renderSedes(lista) {
    var cont = $("sedes"); if (!cont) return;
    var previo = {};
    Array.prototype.forEach.call(cont.querySelectorAll("[data-sede]"), function (n) {
      previo[n.getAttribute("data-sede")] = n.classList.contains("ok");
    });
    vaciar(cont);
    if (!Array.isArray(lista) || !lista.length) { cont.appendChild(el("p", { class: "muted", text: "Sin información de las sedes." })); return; }
    var cambios = [];
    lista.forEach(function (sd) {
      sd = sd || {};
      var sid = sd.sede_id === null || sd.sede_id === undefined ? "" : String(sd.sede_id);
      var art = el("article", { class: "metric-box nodo " + (sd.disponible ? "ok" : "down"), "data-sede": sid }, [
        el("h4", { text: "Sede " + (sid || "—") + " · " + txt(sd.nombre) }),
        el("p", { class: "nodo-cab" }, [badgeMotor(sd.motor), " ", badgeUpDown(!!sd.disponible), sd.ciudad ? " " : null,
          sd.ciudad ? el("span", { class: "badge b-sede", text: String(sd.ciudad) }) : null]),
        el("dl", { class: "datos datos-2" }, [
          el("div", null, [el("dt", { text: "Pacientes" }), el("dd", { text: fmt(sd.total_pacientes) })]),
          el("div", null, [el("dt", { text: "Con FHIR" }), el("dd", { text: fmt(sd.pacientes_con_fhir) })]),
          el("div", null, [el("dt", { text: "Latencia" }), el("dd", { text: esNum(sd.latencia_ms) ? fmt(sd.latencia_ms) + " ms" : "—" })]),
          el("div", null, [el("dt", { text: "Cobertura FHIR" }), el("dd", { text: esNum(sd.porcentaje_cobertura) ? fmt(sd.porcentaje_cobertura) + " %" : "—" })])
        ]),
        barra(sd.porcentaje_cobertura, "Cobertura FHIR de la sede " + sid),
        sd.error ? el("p", { class: "nodo-error mono" }, [ico("alerta"), " " + String(sd.error)]) : null
      ]);
      cont.appendChild(art);
      if (sid in previo && previo[sid] !== !!sd.disponible) {
        destellar(art);
        cambios.push("Sede " + sid + (sd.disponible ? " volvió a estar disponible." : " sin conexión."));
      }
    });
    if (cambios.length) anunciar(cambios.join(" "));
  }

  function filaBarra(etiqueta, valor, max, clsRelleno) {
    var ancho = max > 0 ? Math.round(valor / max * 1000) / 10 : 0;
    var r = el("span", { class: "bh-relleno " + clsRelleno }); r.style.width = ancho + "%";
    return el("li", null, [
      el("span", { class: "bh-etq" }, [etiqueta]),
      el("span", { class: "bh-pista", "aria-hidden": "true" }, [r]),
      el("span", { class: "bh-num", text: fmt(valor) })
    ]);
  }

  function renderBus(bus) {
    bus = bus || {};
    var eg = txt(bus.estado_general, "").toUpperCase();
    var be = $("bus-estado");
    if (be) {
      be.textContent = txt(bus.estado_general, "Sin estado");
      be.className = "badge " + (["UP", "OK", "SALUDABLE"].indexOf(eg) >= 0 ? "b-ok" : (eg ? "b-warn" : "b-neutro"));
    }
    var ul = $("grafico-estados");
    if (ul) {
      var pe = {};
      Object.keys(bus.mensajes_por_estado || {}).forEach(function (k) { pe[String(k).toUpperCase()] = bus.mensajes_por_estado[k]; });
      var claves = ESTADOS.concat(Object.keys(pe).filter(function (k) { return ESTADOS.indexOf(k) < 0; }).sort());
      var max = 0;
      claves.forEach(function (k) { if (esNum(pe[k]) && pe[k] > max) max = pe[k]; });
      vaciar(ul);
      claves.forEach(function (k) {
        ul.appendChild(filaBarra(badgeEstado(k), num(pe[k]), max, "f-" + (ESTADOS.indexOf(k) >= 0 ? k.toLowerCase() : "otro")));
      });
    }
    var dl = $("bus-contadores");
    if (dl) {
      vaciar(dl);
      Object.keys(bus).sort().forEach(function (k) {
        if (!esNum(bus[k])) return;
        var etq = ETQ_BUS[k] || (k.charAt(0).toUpperCase() + k.slice(1)).replace(/_/g, " ");
        dl.appendChild(el("div", null, [el("dt", { text: etq }), el("dd", { text: fmt(bus[k]) })]));
      });
    }
  }

  function renderFhir(f) {
    var caja = $("caja-fhir"), cont = $("grafico-fhir"), est = $("fhir-estado");
    if (!cont) return;
    var hay = !!f && typeof f === "object";
    var disp = hay && !!f.disponible;
    if (caja) caja.classList.toggle("caja-down", hay && !disp);
    if (est) {
      est.textContent = disp ? "Disponible" : (hay ? "No disponible" : "Sin datos");
      est.className = "badge punto " + (disp ? "b-ok" : (hay ? "b-err" : "b-neutro"));
    }
    vaciar(cont);
    var rec = (hay && f.recursos) || {};
    var claves = RECURSOS.filter(function (r) { return r in rec; })
      .concat(Object.keys(rec).filter(function (r) { return RECURSOS.indexOf(r) < 0; }).sort());
    if (disp && claves.length) {
      var max = 0, total = 0;
      claves.forEach(function (r) { var c = num(rec[r]); total += c; if (c > max) max = c; });
      var ul = el("ul", { class: "barras-h", "aria-label": "Recursos FHIR por tipo" });
      claves.forEach(function (r) { ul.appendChild(filaBarra(el("code", { text: r }), num(rec[r]), max, "f-fhir")); });
      cont.appendChild(ul);
      cont.appendChild(el("p", { class: "muted grafico-pie" }, ["Total: ", el("strong", { text: fmt(total) }), " recursos"]));
    } else if (disp) {
      cont.appendChild(el("p", { class: "muted", text: "Sin recursos publicados." }));
    } else {
      cont.appendChild(el("p", { class: "alerta-err" }, [ico("x"), "Servidor FHIR sin respuesta."]));
    }
  }

  function idsDe(tbody) {
    var s = {};
    Array.prototype.forEach.call(tbody.querySelectorAll("tr[data-id]"), function (tr) { var i = tr.getAttribute("data-id"); if (i) s[i] = true; });
    return s;
  }

  function renderActividad(id, items, vacio, fila) {
    var ul = $(id); if (!ul) return;
    vaciar(ul);
    var l = (Array.isArray(items) ? items : []).slice(0, 8);
    if (!l.length) { ul.appendChild(el("li", { class: "vacio", text: vacio })); return; }
    l.forEach(function (x) { ul.appendChild(fila(x || {})); });
  }

  function renderMensajes(lista) {
    renderActividad("act-mensajes", lista, "Sin mensajes recientes.", function (m) {
      return el("li", null, [badgeEstado(m.estado), el("span", { class: "act-texto", text: txt(m.tipo_mensaje) + " · " + sedeTxt(m.sede_origen) }),
        el("time", { class: "act-hora", text: fecha(m.actualizado_en) })]);
    });
    var tb = $("tbody-mensajes"); if (!tb) return;
    var previos = idsDe(tb);
    vaciar(tb);
    if (!Array.isArray(lista) || !lista.length) {
      tb.appendChild(el("tr", null, [el("td", { colspan: 8, class: "vacio", text: "Sin mensajes." })]));
      return;
    }
    lista.forEach(function (m) {
      m = m || {};
      var id = txt(m.mensaje_id, "");
      var tr = el("tr", { "data-id": id, "data-estado": txt(m.estado, "").toUpperCase() }, [
        el("th", { scope: "row" }, [hashCorto(m.mensaje_id)]),
        el("td", null, [badgeEstado(m.estado)]),
        el("td", null, [el("span", { class: "badge b-sede", text: txt(m.formato) })]),
        el("td", null, [el("span", { class: "celda-sede" }, [sedeTxt(m.sede_origen), m.motor ? " " : null, m.motor ? badgeMotor(m.motor) : null])]),
        el("td", { text: txt(m.tipo_mensaje) }),
        el("td", { class: "num-col", text: fmt(m.intentos) }),
        el("td", { class: "nowrap", text: fecha(m.actualizado_en) }),
        el("td", { class: "motivo", text: txt(m.motivo_rechazo) })
      ]);
      if (id && !previos[id]) tr.classList.add("nuevo");
      tb.appendChild(tr);
    });
    filtrarMensajes();
  }

  var selEstado = $("filtro-estado");
  function filtrarMensajes() {
    var tb = $("tbody-mensajes"); if (!tb || !selEstado) return;
    var v = selEstado.value, vis = 0, filas = tb.querySelectorAll("tr[data-estado]");
    Array.prototype.forEach.call(filas, function (tr) {
      var ok = !v || tr.getAttribute("data-estado") === v;
      tr.hidden = !ok; if (ok) vis++;
    });
    var vacia = tb.querySelector("tr.sin-filtro");
    if (filas.length && !vis) {
      if (!vacia) tb.appendChild(el("tr", { class: "sin-filtro" }, [el("td", { colspan: 8, class: "vacio", text: "Ningún mensaje en ese estado." })]));
    } else if (vacia) vacia.parentNode.removeChild(vacia);
    return vis;
  }
  if (selEstado) selEstado.addEventListener("change", function () {
    var vis = filtrarMensajes();
    anunciar(selEstado.value ? fmt(vis) + " mensajes en estado " + selEstado.value.toLowerCase() + "." : "Mostrando todos los mensajes.");
  });

  var integraPrevia = (function () {
    var v = document.querySelector("#verificador .verif");
    return v ? (v.classList.contains("ok") ? true : (v.classList.contains("err") ? false : null)) : null;
  })();

  function renderAuditoria(a) {
    a = a || {};
    renderActividad("act-auditoria", a.eventos, "Sin eventos recientes.", function (ev) {
      return el("li", null, [badgeResultado(ev.resultado), el("span", { class: "act-texto" }, [el("code", { text: txt(ev.tipo_evento) }), " · " + txt(ev.usuario_sistema)]),
        el("time", { class: "act-hora", text: fecha(ev.timestamp) })]);
    });
    var integra = a.cadena_integra === true ? true : (a.cadena_integra === false ? false : null);
    var alt = integra === false ? (a.detalle_alteracion || null) : null;
    var cont = $("verificador");
    if (cont) {
      var clase = integra === true ? "ok" : (integra === false ? "err" : "na");
      var cuerpo = el("div", { class: "verif-cuerpo" }, [
        el("div", { class: "rotulo", text: "Estado de la cadena" }),
        el("div", { class: "estado", text: integra === true ? "ÍNTEGRA" : (integra === false ? "ALERTA: cadena alterada" : "NO DISPONIBLE") }),
        a.estado_verificador ? el("p", { class: "verif-texto", text: String(a.estado_verificador) }) : null
      ]);
      if (alt) {
        cuerpo.appendChild(el("h4", { text: "Primer evento alterado" }));
        cuerpo.appendChild(el("dl", { class: "datos" }, [
          el("div", null, [el("dt", { text: "Índice" }), el("dd", null, [el("strong", { text: txt(alt.indice) })])]),
          el("div", null, [el("dt", { text: "Motivo" }), el("dd", { text: txt(alt.motivo) })]),
          el("div", null, [el("dt", { text: "Usuario (registrado)" }), el("dd", { text: txt(alt.usuario) })]),
          el("div", null, [el("dt", { text: "Tipo de evento" }), el("dd", { text: txt(alt.tipo_evento) })]),
          el("div", null, [el("dt", { text: "Fecha del evento" }), el("dd", { text: fecha(alt.timestamp) })])
        ]));
      }
      var verif = el("div", { class: "verif " + clase }, [
        el("span", { class: "icono" }, [ico(integra === true ? "escudo-ok" : (integra === false ? "alerta" : "info"))]),
        cuerpo
      ]);
      var datos = el("dl", { class: "datos" }, [
        el("div", null, [el("dt", { text: "Eventos registrados" }), el("dd", { text: fmt(a.total_eventos_registrados) })]),
        el("div", null, [el("dt", { text: "Eventos en espera" }), el("dd", { text: fmt(a.eventos_en_espera) })]),
        el("div", null, [el("dt", { text: "Base central" }), el("dd", null, [badgeUpDown(!!a.disponible)])]),
        el("div", { class: "ancho" }, [el("dt", { text: "Último hash de la cadena" }), el("dd", null, [chipSello(a.ultimo_hash)])])
      ]);
      vaciar(cont);
      cont.appendChild(verif);
      cont.appendChild(datos);
      if (integra !== integraPrevia) {
        destellar(verif);
        if (integra === false) anunciar("ALERTA: la cadena de auditoría fue alterada" + (alt && alt.indice !== undefined && alt.indice !== null ? "; primer evento alterado: " + alt.indice + "." : "."));
        else if (integra === true && integraPrevia === false) anunciar("La cadena de auditoría vuelve a estar íntegra.");
        integraPrevia = integra;
      }
    }
    var tb = $("tbody-auditoria");
    if (tb) {
      var previos = idsDe(tb);
      vaciar(tb);
      var evs = Array.isArray(a.eventos) ? a.eventos : [];
      if (!evs.length) {
        tb.appendChild(el("tr", null, [el("td", { colspan: 8, class: "vacio", text: "Sin eventos de auditoría." })]));
      }
      evs.forEach(function (ev) {
        ev = ev || {};
        var id = txt(ev.indice, "");
        var esAlt = !!(alt && alt.indice !== null && alt.indice !== undefined && String(ev.indice) === String(alt.indice));
        var tr = el("tr", { "data-id": id, class: esAlt ? "fila-alterada" : null }, [
          el("th", { scope: "row", class: "num-col" }, [txt(ev.indice), esAlt ? " " : null, esAlt ? el("span", { class: "badge b-err", text: "alterado" }) : null]),
          el("td", { class: "nowrap", text: fecha(ev.timestamp) }),
          el("td", { text: txt(ev.usuario_sistema) }),
          el("td", { text: txt(ev.rol) }),
          el("td", null, [el("code", { text: txt(ev.tipo_evento) })]),
          el("td", { class: "motivo mono", text: txt(ev.recurso_afectado) }),
          el("td", null, [badgeResultado(ev.resultado)]),
          el("td", null, [hashCorto(ev.hash_propio)])
        ]);
        if (id && !previos[id] && !esAlt) tr.classList.add("nuevo");
        tb.appendChild(tr);
      });
    }
  }

  /* 5. Pacientes ----------------------------------------------------------- */
  var qRenderizada = "";
  var pendiente = null; // { doc, hasta } paciente recién registrado que hay que resaltar al aparecer

  function renderPacientes(d) {
    var tb = $("tbody-pacientes"); if (!tb) return;
    var lista = Array.isArray(d.pacientes) ? d.pacientes : [];
    var total = esNum(d.total) ? d.total : lista.length;
    var mismaBusqueda = qRenderizada === q;
    var conteo = $("pac-conteo");
    if (conteo) conteo.textContent = "Mostrando " + fmt(lista.length) + " de " + fmt(total) + (q ? " · búsqueda «" + q + "»" : "");

    var inc = $("pac-incompleto"), incT = $("pac-incompleto-texto");
    var caidas = Array.isArray(d.sedes_no_disponibles) ? d.sedes_no_disponibles : [];
    if (inc && incT) {
      inc.hidden = !caidas.length;
      incT.textContent = caidas.length ? "Lista incompleta: sin conexión con " + caidas.map(sedeTxt).join(", ") + "." : "";
    }

    // Conservar el foco si estaba en un enlace de la tabla.
    var act = document.activeElement, focoDoc = null;
    if (act && tb.contains(act)) { var trf = act.closest("tr"); focoDoc = trf ? trf.getAttribute("data-doc") : null; }

    var previos = {};
    Array.prototype.forEach.call(tb.querySelectorAll("tr[data-doc]"), function (tr) { previos[tr.getAttribute("data-doc")] = true; });
    vaciar(tb);
    if (!lista.length) {
      tb.appendChild(el("tr", null, [el("td", { colspan: 10, class: "vacio", text: q ? "Ningún paciente coincide con «" + q + "»." : "No hay pacientes registrados." })]));
    }
    var registrado = null;
    lista.forEach(function (p) {
      p = p || {};
      var doc = txt(p.documento_id, "");
      var sedes = el("span", { class: "sedes-celda" });
      (Array.isArray(p.sedes) ? p.sedes : []).forEach(function (s) {
        s = s || {};
        var b = el("span", {
          class: "badge " + (s.motor === "mongodb" ? "b-mongo" : (s.motor === "postgresql" ? "b-pg" : "b-neutro")),
          title: "Sede " + txt(s.sede_id) + " · " + motorNombre(s.motor) + " · " + fmt(num(s.atenciones)) + " atenciones" + (s.en_fhir ? " · en FHIR" : "")
        }, [ico(s.motor === "mongodb" ? "hoja" : "db"), "S" + txt(s.sede_id)]);
        if (s.en_fhir) b.appendChild(el("span", { class: "fhir-mini", text: "✓FHIR" }));
        b.appendChild(el("span", { class: "sr-only", text: " " + motorNombre(s.motor) + (s.en_fhir ? ", en FHIR" : "") }));
        sedes.appendChild(b);
      });
      if (!sedes.firstChild) sedes.appendChild(document.createTextNode("—"));
      var edad = "—";
      if (p.edad !== null && p.edad !== undefined && p.edad !== "") {
        var u = p.unidad_edad !== null && p.unidad_edad !== undefined ? UNIDAD[String(p.unidad_edad)] : "";
        edad = String(p.edad) + (u ? " " + String(u).toLowerCase() : "");
      }
      var enlace = doc ? el("a", { href: "/reporte?buscar_doc=" + encodeURIComponent(doc) }, ["Ver reporte", el("span", { class: "sr-only", text: " de " + txt(p.nombre_completo, doc) })]) : null;
      var tr = el("tr", { "data-doc": doc }, [
        el("th", { scope: "row", class: "mono", text: txt(p.documento_id) }),
        el("td", { text: txt(p.nombre_completo) }),
        el("td", { text: p.sexo ? txt(SEXO[p.sexo], p.sexo) : "—" }),
        el("td", { class: "nowrap", text: edad }),
        el("td", { text: txt(p.municipio_residencia) }),
        el("td", null, [sedes]),
        el("td", { class: "num-col", text: fmt(p.total_atenciones) }),
        el("td", { class: "nowrap", text: fecha(p.ultima_atencion) }),
        el("td", null, [p.en_fhir ? el("span", { class: "badge b-ok" }, [ico("check"), "En FHIR"]) : el("span", { class: "badge b-neutro", text: "Sin FHIR" })]),
        el("td", { class: "nowrap" }, [enlace])
      ]);
      if (pendiente && doc && doc === pendiente.doc) { tr.classList.add("registrado"); registrado = tr; }
      else if (mismaBusqueda && doc && !previos[doc]) tr.classList.add("nuevo");
      tb.appendChild(tr);
      if (focoDoc && doc === focoDoc && enlace) enlace.focus({ preventScroll: true });
    });

    if (registrado) {
      var nombre = registrado.children[1] ? registrado.children[1].textContent : pendiente.doc;
      anunciar("El paciente " + nombre + " (documento " + pendiente.doc + ") ya aparece en la lista de pacientes.");
      pendiente = null;
      var caja = registrado.closest(".tabla-scroll");
      if (caja) {
        var top = registrado.offsetTop - caja.clientHeight / 3;
        try { caja.scrollTo({ top: Math.max(0, top), behavior: reducido ? "auto" : "smooth" }); } catch (e) { caja.scrollTop = Math.max(0, top); }
      }
    } else if (pendiente && Date.now() > pendiente.hasta) {
      pendiente = null;
    }
    if (!mismaBusqueda) {
      anunciar(q ? fmt(lista.length) + (lista.length === 1 ? " paciente encontrado" : " pacientes encontrados") + " para «" + q + "»." : "Mostrando todos los pacientes (" + fmt(lista.length) + ").");
    }
    qRenderizada = q;
  }

  /* Búsqueda con espera de 300 ms */
  var inputQ = $("q"), esperaQ = null;
  function buscarAhora() {
    clearTimeout(esperaQ);
    var nueva = (inputQ.value || "").trim();
    if (nueva === q) return;
    q = nueva;
    ejecutar("pacientes");
  }
  if (inputQ) {
    inputQ.addEventListener("input", function () { clearTimeout(esperaQ); esperaQ = setTimeout(buscarAhora, 300); });
    var fb = $("form-buscar");
    if (fb) fb.addEventListener("submit", function (e) { e.preventDefault(); buscarAhora(); });
  }

  /* 6. Registro de pacientes ---------------------------------------------- */
  var form = $("form-registro");
  var CAMPOS = ["sede_id", "tipo_documento", "documento_id", "nombres", "apellidos", "fecha_nacimiento", "sexo",
    "municipio_residencia", "zona_residencia", "direccion_residencia", "telefono", "correo_electronico",
    "entidad_salud", "modalidad_entrega", "entorno_atencion", "via_ingreso", "causa_atencion",
    "clasificacion_triage", "cie10_codigo", "descripcion_cie10"];
  var RE_DOC = /^\d{4,15}$/;
  var RE_CIE = /^[A-Z][0-9]{2}(\.[0-9]{1,4})?$/;
  var RE_CORREO = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function campo(n) { return $("r_" + n); }
  function valor(n) { var c = campo(n); return c ? String(c.value || "").trim() : ""; }
  function hoyISO() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  var ETIQUETAS = {
    sede_id: "Sede que admite", documento_id: "Número de documento", nombres: "Nombres", apellidos: "Apellidos",
    fecha_nacimiento: "Fecha de nacimiento", sexo: "Sexo", correo_electronico: "Correo electrónico", cie10_codigo: "Diagnóstico CIE-10"
  };
  function errorDe(n) {
    var v = valor(n);
    switch (n) {
      case "sede_id": return /^[123]$/.test(v) ? "" : "Seleccione la sede (1, 2 o 3).";
      case "documento_id": return !v ? "Escriba el número de documento." : (RE_DOC.test(v) ? "" : "Solo dígitos, entre 4 y 15.");
      case "nombres": return v ? "" : "Escriba los nombres.";
      case "apellidos": return v ? "" : "Escriba los apellidos.";
      case "fecha_nacimiento":
        if (!v) return "Indique la fecha de nacimiento.";
        if (!/^\d{4}-\d{2}-\d{2}$/.test(v) || isNaN(Date.parse(v + "T00:00:00"))) return "Use el formato AAAA-MM-DD.";
        if (v > hoyISO()) return "La fecha no puede ser futura.";
        if (v < "1900-01-01") return "La fecha es anterior a 1900.";
        return "";
      case "sexo": return ["M", "F", "O"].indexOf(v) >= 0 ? "" : "Seleccione el sexo.";
      case "correo_electronico": return !v || RE_CORREO.test(v) ? "" : "Correo electrónico no válido.";
      case "cie10_codigo": return !v || RE_CIE.test(v.toUpperCase()) ? "" : "Formato CIE-10: letra, dos dígitos y decimales opcionales (ej. J45.9).";
      default: return "";
    }
  }
  function marcar(n, msg) {
    var c = campo(n), e = $("e_" + n);
    if (c) { if (msg) c.setAttribute("aria-invalid", "true"); else c.removeAttribute("aria-invalid"); }
    if (e) e.textContent = msg || "";
  }
  function validar() {
    var errores = [];
    Object.keys(ETIQUETAS).forEach(function (n) {
      var m = errorDe(n);
      marcar(n, m);
      if (m) errores.push({ campo: n, msg: m });
    });
    var caja = $("reg-errores");
    if (caja) {
      vaciar(caja);
      if (errores.length) {
        var ul = el("ul");
        errores.forEach(function (er) {
          var a = el("a", { href: "#r_" + er.campo, text: ETIQUETAS[er.campo] + ": " + er.msg });
          a.addEventListener("click", function (ev) { ev.preventDefault(); var c = campo(er.campo); if (c) c.focus(); });
          ul.appendChild(el("li", null, [a]));
        });
        caja.appendChild(ico("x"));
        caja.appendChild(el("strong", { text: errores.length === 1 ? "Corrija 1 campo:" : "Corrija " + errores.length + " campos:" }));
        caja.appendChild(ul);
        caja.hidden = false;
      } else caja.hidden = true;
    }
    return errores;
  }

  function cuerpoRegistro() {
    var datos = {};
    CAMPOS.forEach(function (n) {
      var v = valor(n);
      if (n === "cie10_codigo") v = v.toUpperCase();
      if (n === "sede_id") { datos.sede_id = parseInt(v, 10); return; }
      if (v !== "") datos[n] = v; // los opcionales vacíos no se envían
    });
    return datos;
  }

  function sedeNombre(sd) { var d = SEDES[String(sd)]; return d ? (d.nombre || "Sede " + sd) : (sd !== undefined && sd !== null ? "Sede " + sd : "la sede"); }
  function textoMotivos(m) {
    return (Array.isArray(m) ? m : []).map(function (x) { return typeof x === "string" ? x : (x && (x.msg || x.mensaje || x.motivo)) || JSON.stringify(x); });
  }

  /* Credenciales de un portal o de una cuenta nueva: se muestran una sola vez. */
  function bloqueCredenciales(titulo, usuario, clave, nota) {
    var dl = el("dl", { class: "datos" });
    if (usuario) dl.appendChild(el("div", null, [el("dt", { text: "Usuario" }), el("dd", null, [chipSello(usuario, "usuario", "usuario")])]));
    if (clave) dl.appendChild(el("div", null, [el("dt", { text: "Contraseña temporal" }), el("dd", null, [chipSello(clave, "contraseña temporal")])]));
    return el("div", { class: "credenciales" }, [el("h3", { text: titulo }), dl,
      el("p", { class: "credenciales-nota" }, [ico("info"), nota || "Se pedirá cambiarla al primer ingreso. Esta contraseña se muestra una sola vez."])]);
  }
  function credencialesPaciente(cp) {
    if (!cp || typeof cp !== "object" || !cp.username) return null;
    if (cp.clave_temporal) return bloqueCredenciales("Cuenta del portal del paciente", String(cp.username), String(cp.clave_temporal));
    if (cp.error) return el("p", { class: "credenciales-nota" }, [ico("alerta"), "No se pudo crear la cuenta del portal del paciente: " + String(cp.error)]);
    return el("p", { class: "credenciales-nota" }, [ico("usuario"), "Cuenta del portal del paciente: usuario ", el("code", { text: String(cp.username) }), " (ya existente)."]);
  }

  function tarjetaResultado(r, http) {
    r = r || {};
    var est = txt(r.estado, "error").toLowerCase();
    var motivos = textoMotivos(r.motivos);
    var conf = {
      entregado: ["ok", "check", "Paciente registrado", "Atención abierta en " + sedeNombre(r.sede)],
      reintentando: ["warn", "reloj", "En cola de reintento", "Se enviará a " + sedeNombre(r.sede) + " cuando la sede responda."],
      duplicado: ["warn", "info", "Ya registrado", ""],
      rechazado: ["err", "x", "Rechazado" + (motivos.length ? ": " + motivos.join("; ") : ""), ""]
    }[est] || ["err", "x", "No se pudo registrar", r.motivo ? String(r.motivo) : ""];
    var cuerpo = el("div", { class: "resultado-cuerpo" }, [
      el("h3", { class: "resultado-titulo", text: conf[2] }),
      conf[3] ? el("p", { class: "resultado-sub", text: conf[3] }) : null
    ]);
    var dl = el("dl", { class: "datos" });
    function dato(et, valorNodo) { dl.appendChild(el("div", null, [el("dt", { text: et }), el("dd", null, [valorNodo])])); }
    if (r.documento) dato("Documento", String(r.documento));
    if (r.numero_visita) dato("N.º de atención", el("span", { class: "mono", text: String(r.numero_visita) }));
    if (r.mensaje_id) dato("N.º de mensaje", el("span", { class: "mono", text: String(r.mensaje_id) }));
    if (r.sede !== undefined && r.sede !== null) {
      var sd = el("span", { class: "celda-sede" }, [sedeTxt(r.sede)]);
      var m = r.motor || (SEDES[String(r.sede)] || {}).motor;
      if (m) { sd.appendChild(document.createTextNode(" ")); sd.appendChild(badgeMotor(m)); }
      dato("Sede", sd);
    }
    var recursos = Array.isArray(r.recursos_fhir) ? r.recursos_fhir : [];
    if (recursos.length) {
      dato("FHIR", el("span", { class: "mono", text: recursos.map(function (x) {
        return typeof x === "string" ? x : (x && typeof x === "object" ? txt(x.resourceType, "?") + (x.id ? "/" + x.id : "") : String(x));
      }).join(" · ") }));
    }
    if (dl.firstChild) cuerpo.appendChild(dl);
    var cred = credencialesPaciente(r.cuenta_paciente);
    if (cred) cuerpo.appendChild(cred);
    if (r.sello) {
      cuerpo.appendChild(el("h3", { text: "Código de verificación" }));
      cuerpo.appendChild(chipSello(r.sello));
    }
    if (http && est === "error") cuerpo.appendChild(el("p", { class: "muted", style: "margin:8px 0 0;", text: "HTTP " + http }));
    return { nodo: el("div", { class: "resultado " + conf[0], role: "status" }, [el("span", { class: "icono" }, [ico(conf[1], "ico-lg")]), cuerpo]), estado: est, titulo: conf[2] };
  }

  function mostrarResultado(r, http) {
    var cont = $("reg-resultado"); if (!cont) return null;
    var t = tarjetaResultado(r, http);
    vaciar(cont);
    cont.appendChild(t.nodo);
    try { cont.scrollIntoView({ block: "nearest", behavior: reducido ? "auto" : "smooth" }); } catch (e) { /* sin soporte */ }
    var cp = r && r.cuenta_paciente;
    anunciar(t.titulo + (r && r.documento ? " (documento " + r.documento + ")" : "") + "." +
      (cp && cp.clave_temporal ? " Se creó la cuenta del portal del paciente; la contraseña temporal se muestra en pantalla." : ""));
    return t.estado;
  }

  var enviando = false;
  function ponerEnviando(si) {
    var b = $("btn-registrar"); if (!b) return;
    enviando = si;
    b.disabled = si || expirada;
    if (form) form.setAttribute("aria-busy", si ? "true" : "false");
    var etq = b.querySelector("span");
    var svg = b.querySelector("svg");
    if (etq) etq.textContent = si ? "Enviando…" : "Registrar paciente";
    if (svg) b.replaceChild(si ? ico("girar", "girando") : ico("enviar"), svg);
  }

  if (form) {
    var fn = campo("fecha_nacimiento");
    if (fn) fn.max = hoyISO();
    var cie = campo("cie10_codigo");
    if (cie) cie.addEventListener("blur", function () { cie.value = cie.value.trim().toUpperCase(); });
    Object.keys(ETIQUETAS).forEach(function (n) {
      var c = campo(n); if (!c) return;
      var revisar = function () { if (c.getAttribute("aria-invalid") === "true") marcar(n, errorDe(n)); };
      c.addEventListener("input", revisar);
      c.addEventListener("change", revisar);
      c.addEventListener("blur", function () { if (valor(n) !== "" || c.getAttribute("aria-invalid") === "true") marcar(n, errorDe(n)); });
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (enviando || expirada) return;
      var errores = validar();
      if (errores.length) {
        var caja = $("reg-errores");
        if (caja) caja.focus();
        anunciar("El formulario tiene " + errores.length + (errores.length === 1 ? " error." : " errores."));
        return;
      }
      var datos = cuerpoRegistro();
      ponerEnviando(true);
      pedir("/api/panel/registrar", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(datos)
      }).then(function (r) {
        var d = r.datos && typeof r.datos === "object" ? r.datos : null;
        if (d && d.estado) return mostrarResultado(d, r.status);
        if (r.status === 422) {
          var det = d && Array.isArray(d.detail) ? d.detail.map(function (x) {
            var loc = Array.isArray(x.loc) ? x.loc.filter(function (p) { return p !== "body"; }).join(".") : "";
            return (loc ? loc + ": " : "") + (x.msg || "valor no válido");
          }) : [d && d.detail ? String(d.detail) : "Datos no válidos."];
          return mostrarResultado({ estado: "rechazado", motivos: det, documento: datos.documento_id }, r.status);
        }
        return mostrarResultado({ estado: "error", motivo: (d && (d.motivo || d.detail)) ? String(d.motivo || d.detail) : "El servidor respondió con un error.", documento: datos.documento_id }, r.status);
      }, function (err) {
        if (err && err.sesion) {
          expirar();
          return mostrarResultado({ estado: "error", motivo: "Sesión expirada, vuelva a iniciar sesión." });
        }
        return mostrarResultado({ estado: "error", motivo: "No se pudo contactar al servidor (" + ((err && err.message) || "error de red") + ")." });
      }).then(function (estado) {
        ponerEnviando(false);
        if (["entregado", "duplicado", "reintentando"].indexOf(estado) >= 0) {
          pendiente = { doc: datos.documento_id, hasta: Date.now() + 60000 };
          if (inputQ && q) { inputQ.value = ""; q = ""; }
          if (estado === "entregado") {
            var sede = valor("sede_id");
            form.reset();
            campo("sede_id").value = sede;
            if (fn) fn.max = hoyISO();
          }
          actualizarTodo();
        }
      });
    });

    /* Datos de ejemplo: sintéticos, aleatorios, plausibles para la región */
    var NOMBRES_F = ["María José", "Ana Lucía", "Luisa Fernanda", "Valentina", "Sofía", "Daniela", "Yuranis", "Karen Margarita"];
    var NOMBRES_M = ["Juan Carlos", "Andrés Felipe", "Luis Alberto", "José David", "Carlos Mario", "Miguel Ángel", "Jesús Alberto", "Sebastián"];
    var APELLIDOS = ["Pérez", "Gómez", "Martínez", "Díaz", "Rodríguez", "Herrera", "Mercado", "Salgado", "Vergara", "Montes",
      "Arrieta", "Pacheco", "Hernández", "Ruiz", "Banquez", "Julio", "Tovar", "Meza", "Olivera", "Barrios"];
    var MUNICIPIOS = ["70001", "13001", "70215"];
    var EPS = ["Nueva EPS", "Coosalud EPS", "Sanitas EPS", "Salud Total"];
    var CASOS = [
      ["J45.9", "Asma, no especificada", "Crisis asmática con dificultad respiratoria"],
      ["I10", "Hipertensión esencial (primaria)", "Cifras tensionales elevadas y cefalea"],
      ["E11.9", "Diabetes mellitus tipo 2 sin complicaciones", "Control de glucemia descompensada"],
      ["A09", "Diarrea y gastroenteritis de presunto origen infeccioso", "Deposiciones líquidas y fiebre"],
      ["R51", "Cefalea", "Cefalea intensa de dos días de evolución"],
      ["J18.9", "Neumonía, no especificada", "Tos productiva, fiebre y dificultad para respirar"],
      ["N39.0", "Infección de vías urinarias, sitio no especificado", "Disuria y dolor suprapúbico"],
      ["M54.5", "Lumbago no especificado", "Dolor lumbar tras esfuerzo físico"]
    ];
    var CALLES = ["Calle", "Carrera", "Diagonal", "Transversal"];
    function azar(lista) { return lista[Math.floor(Math.random() * lista.length)]; }
    function entre(a, b) { return a + Math.floor(Math.random() * (b - a + 1)); }
    function asciiMin(s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z]/g, ""); }
    function poner(n, v) {
      var c = campo(n); if (!c) return;
      if (c.tagName === "SELECT") {
        var ok = Array.prototype.some.call(c.options, function (o) { return o.value === v; });
        c.value = ok ? v : (c.options.length > 1 ? c.options[1].value : "");
      } else c.value = v;
      marcar(n, "");
    }
    var be = $("btn-ejemplo");
    if (be) be.addEventListener("click", function () {
      var mujer = Math.random() < 0.5;
      var nombres = azar(mujer ? NOMBRES_F : NOMBRES_M);
      var ap1 = azar(APELLIDOS), ap2 = azar(APELLIDOS);
      while (ap2 === ap1) ap2 = azar(APELLIDOS);
      var anio = entre(1942, 2021), mes = entre(1, 12), dia = entre(1, 28);
      var edad = new Date().getFullYear() - anio;
      var caso = azar(CASOS);
      var sedes = Object.keys(SEDES).length ? Object.keys(SEDES) : ["1", "2", "3"];
      poner("sede_id", azar(sedes));
      poner("tipo_documento", edad >= 18 ? "CC" : (edad >= 7 ? "TI" : "RC"));
      poner("documento_id", String(entre(1, 9)) + String(Math.floor(Math.random() * 1e9)).padStart(9, "0").slice(0, entre(5, 9)));
      poner("nombres", nombres);
      poner("apellidos", ap1 + " " + ap2);
      poner("fecha_nacimiento", anio + "-" + String(mes).padStart(2, "0") + "-" + String(dia).padStart(2, "0"));
      poner("sexo", mujer ? "F" : "M");
      poner("municipio_residencia", azar(MUNICIPIOS));
      poner("zona_residencia", Math.random() < 0.8 ? "01" : "02");
      poner("direccion_residencia", azar(CALLES) + " " + entre(1, 80) + " # " + entre(1, 60) + "-" + entre(10, 99));
      poner("telefono", "3" + String(entre(0, 2)) + String(entre(0, 9)) + String(entre(1000000, 9999999)));
      poner("correo_electronico", asciiMin(nombres.split(" ")[0]) + "." + asciiMin(ap1) + entre(1, 99) + "@correo-ejemplo.co");
      poner("entidad_salud", azar(EPS));
      poner("modalidad_entrega", "01");
      poner("entorno_atencion", azar(["01", "02"]));
      poner("via_ingreso", azar(["01", "02"]));
      poner("causa_atencion", caso[2]);
      poner("clasificacion_triage", String(entre(2, 5)));
      poner("cie10_codigo", caso[0]);
      poner("descripcion_cie10", caso[1]);
      var caja = $("reg-errores"); if (caja) caja.hidden = true;
      anunciar("Formulario lleno con datos de ejemplo: " + nombres + " " + ap1 + " " + ap2 + ".");
    });
  }

  /* 7. Controles: pausa, actualizar, visibilidad --------------------------- */
  var bp = $("btn-pausa"), ba = $("btn-actualizar");
  function pintarPausa() {
    if (!bp) return;
    bp.setAttribute("aria-pressed", pausado ? "true" : "false");
    var svg = bp.querySelector("svg"), sp = bp.querySelector("span");
    if (svg) bp.replaceChild(ico(pausado ? "play" : "pausa"), svg);
    if (sp) sp.textContent = pausado ? "Reanudar" : "Pausar";
  }
  if (bp) {
    bp.hidden = false;
    bp.addEventListener("click", function () {
      if (expirada) return;
      pausado = !pausado;
      pintarPausa();
      if (pausado) {
        Object.keys(fuentes).forEach(function (k) { clearTimeout(fuentes[k].timer); fuentes[k].timer = null; });
        anunciar("Actualización automática en pausa.");
      } else {
        anunciar("Actualización automática reanudada.");
        actualizarTodo();
      }
      pintarVivo();
    });
  }
  if (ba) {
    ba.setAttribute("role", "button");
    ba.addEventListener("click", function (e) {
      e.preventDefault();
      if (expirada) return;
      actualizarTodo().then(function () {
        if (expirada) return;
        if (hayErrores()) return; // el aviso ya se anunció
        anunciar("Panel actualizado.");
      });
    });
    ba.addEventListener("keydown", function (e) { if (e.key === " ") { e.preventDefault(); ba.click(); } });
  }
  document.addEventListener("visibilitychange", function () {
    if (document.hidden || pausado || expirada) return;
    Object.keys(fuentes).forEach(function (k) {
      if (activa(k) && Date.now() - fuentes[k].ultimoOk > fuentes[k].cada) ejecutar(k);
    });
  });

  var vivo = $("vivo");
  if (vivo) vivo.hidden = false;
  pintarVivo();
  setInterval(pintarVivo, 1000);
  /* 8. Usuarios ------------------------------------------------------------ */
  var ROL_CLS = { paciente: "b-info", admisionista: "b-ok", medico: "b-vio", auditor: "b-ind", administrador: "b-warn" };
  var RE_USUARIO = /^[a-z0-9._-]{4,40}$/;
  var pendienteU = null;
  function arr(v) { return Array.isArray(v) ? v : []; }
  function normalizarAlcance(d) {
    return { puede_gestionar: d.puede_gestionar === true, sedes_gestionables: arr(d.sedes_gestionables).map(Number),
      roles_asignables: arr(d.roles_asignables).map(String), cargado: true };
  }
  function puedeTocar(u) {
    var a = ALCANCE;
    return !!a.puede_gestionar && arr(a.roles_asignables).indexOf(u.rol) >= 0 &&
      (arr(a.sedes_gestionables).length > 1 || arr(a.sedes_gestionables).indexOf(Number(u.sede_id)) >= 0);
  }

  function filaUsuario(u) {
    u = u || {};
    var nombre = txt(u.username, "");
    var inactivo = u.activo === false;
    var estado = el("td", null, [el("span", { class: "badge punto " + (inactivo ? "b-neutro" : "b-ok"), text: inactivo ? "Inactivo" : "Activo" })]);
    if (u.debe_cambiar_clave) { estado.appendChild(document.createTextNode(" ")); estado.appendChild(el("span", { class: "badge b-warn", text: "Clave temporal" })); }
    estado.appendChild(el("small", { class: "sub-celda", text: "Último acceso: " + (u.ultimo_acceso ? fecha(u.ultimo_acceso) : "nunca") }));
    var registro = el("td", { class: "registro-celda" }, [
      el("span", { class: "badge b-sede", text: ORIGENES[u.origen] || txt(u.origen) }),
      el("small", { text: (u.creado_por ? "por " + u.creado_por + " · " : "") + fecha(u.creado_en) })
    ]);
    var acc = el("td", { class: "acciones-fila" });
    if (puedeTocar(u) && nombre) {
      var caja = el("span", { class: "solo-js" });
      if (nombre !== YO) {
        caja.appendChild(el("button", { type: "button", class: "btn btn-sec btn-sm", "data-accion": "estado", "data-activo": inactivo ? "true" : "false", "data-usuario": nombre },
          [inactivo ? "Activar" : "Desactivar", el("span", { class: "sr-only", text: " a " + nombre })]));
      }
      caja.appendChild(el("button", { type: "button", class: "btn btn-sec btn-sm", "data-accion": "restablecer", "data-usuario": nombre },
        ["Restablecer clave", el("span", { class: "sr-only", text: " de " + nombre })]));
      acc.appendChild(caja);
    } else acc.appendChild(el("span", { class: "muted", text: "—" }));
    return el("tr", { "data-usuario": nombre, class: inactivo ? "fila-inactiva" : null }, [
      el("th", { scope: "row" }, [el("span", { class: "mono", text: txt(u.username) }),
        u.documento_id ? el("small", { class: "sub-celda", text: "Doc. " + u.documento_id }) : null]),
      el("td", { text: txt(u.nombre_completo) }),
      el("td", null, [el("span", { class: "badge " + (ROL_CLS[u.rol] || "b-neutro"), text: ROLES[u.rol] || txt(u.rol) })]),
      el("td", { text: u.sede_id === null || u.sede_id === undefined || u.sede_id === "" ? "Toda la red" : sedeTxt(Number(u.sede_id)) }),
      estado, registro,
      acc
    ]);
  }

  var tbU = $("tbody-usuarios");
  function renderUsuarios(d) {
    ALCANCE = normalizarAlcance(d || {});
    actualizarFormUsuario();
    var lista = arr(d && d.usuarios);
    var conteo = $("usr-conteo");
    if (conteo) conteo.textContent = fmt(lista.length) + (lista.length === 1 ? " usuario" : " usuarios");
    var sl = $("usr-solo-lectura"); if (sl) sl.hidden = ALCANCE.puede_gestionar;
    if (!tbU) return;
    var act = document.activeElement, foco = null;
    if (act && tbU.contains(act) && act.getAttribute("data-accion")) foco = [act.getAttribute("data-usuario"), act.getAttribute("data-accion")];
    vaciar(tbU);
    if (!lista.length) {
      var hayFiltro = filtroU.q || filtroU.rol || filtroU.sede;
      tbU.appendChild(el("tr", null, [el("td", { colspan: 7, class: "vacio", text: hayFiltro ? "Ningún usuario coincide con el filtro." : "Sin usuarios." })]));
    }
    var nuevo = null;
    lista.forEach(function (u) {
      var tr = filaUsuario(u);
      if (pendienteU && u && u.username === pendienteU) { tr.classList.add("registrado"); nuevo = tr; }
      tbU.appendChild(tr);
    });
    if (nuevo) {
      pendienteU = null;
      var cajaT = nuevo.closest(".tabla-scroll");
      if (cajaT) cajaT.scrollTop = Math.max(0, nuevo.offsetTop - cajaT.clientHeight / 3);
    }
    if (foco) {
      var b = tbU.querySelector('button[data-usuario="' + (window.CSS && CSS.escape ? CSS.escape(foco[0]) : foco[0]) + '"][data-accion="' + foco[1] + '"]');
      if (b) b.focus({ preventScroll: true });
    }
  }

  /* Filtros (consulta al servidor) */
  var ufQ = $("uf_q"), ufRol = $("uf_rol"), ufSede = $("uf_sede"), esperaU = null;
  function aplicarFiltroU() {
    filtroU = { q: ufQ ? ufQ.value.trim() : "", rol: ufRol ? ufRol.value : "", sede: ufSede ? ufSede.value : "" };
    ejecutar("usuarios");
  }
  if (ufQ) ufQ.addEventListener("input", function () { clearTimeout(esperaU); esperaU = setTimeout(aplicarFiltroU, 300); });
  [ufRol, ufSede].forEach(function (s) { if (s) s.addEventListener("change", aplicarFiltroU); });
  var ffu = $("form-filtro-usuarios");
  if (ffu) ffu.addEventListener("submit", function (e) { e.preventDefault(); clearTimeout(esperaU); aplicarFiltroU(); });

  /* Diálogo de confirmación */
  function confirmar(titulo, texto, boton, peligro) {
    var d = $("dlg-confirmar");
    if (!d || typeof d.showModal !== "function") return Promise.resolve(window.confirm(titulo + "\n\n" + texto));
    $("dlg-titulo").textContent = titulo;
    $("dlg-texto").textContent = texto;
    var ok = $("dlg-ok");
    ok.textContent = boton;
    ok.className = "btn" + (peligro ? " btn-danger" : "");
    var origen = document.activeElement;
    return new Promise(function (resolver) {
      d.returnValue = "";
      d.addEventListener("close", function alCerrar() {
        d.removeEventListener("close", alCerrar);
        resolver(d.returnValue === "confirmar");
        if (origen && document.body.contains(origen)) origen.focus();
      });
      d.showModal();
    });
  }

  function postJSON(url, cuerpo) {
    return pedir(url, { method: "POST", permitir403: true, headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(cuerpo || {}) });
  }
  function motivosDe(r) {
    var d = r && r.datos;
    if (d && Array.isArray(d.motivos) && d.motivos.length) return textoMotivos(d.motivos);
    if (d && Array.isArray(d.detail)) return d.detail.map(function (x) { return (x && x.msg) || "valor no válido"; });
    if (d && d.detail) return [String(d.detail)];
    return ["El servidor respondió con un error (HTTP " + (r ? r.status : "?") + ")."];
  }

  function mostrarUsr(tipo, titulo, extra, enfocar) {
    var cont = $("usr-resultado"); if (!cont) return;
    vaciar(cont);
    var cuerpo = el("div", { class: "resultado-cuerpo" }, [el("h3", { class: "resultado-titulo", text: titulo })]);
    (extra || []).forEach(function (n) { if (n) cuerpo.appendChild(n); });
    cont.appendChild(el("div", { class: "resultado " + tipo, role: "status" },
      [el("span", { class: "icono" }, [ico(tipo === "ok" ? "check" : (tipo === "warn" ? "alerta" : "x"), "ico-lg")]), cuerpo]));
    if (enfocar) { try { cont.focus({ preventScroll: true }); cont.scrollIntoView({ block: "nearest", behavior: reducido ? "auto" : "smooth" }); } catch (e) { /* sin soporte */ } }
    anunciar(titulo + ".");
  }
  function errorRed(err) {
    if (err && err.sesion) { expirar(); return; }
    mostrarUsr("err", "No se pudo contactar al servidor", [el("p", { class: "resultado-sub", text: (err && err.message) || "error de red" })], true);
  }

  if (tbU) tbU.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("button[data-accion]") : null;
    if (!b || expirada || b.disabled) return;
    var nombre = b.getAttribute("data-usuario"), accion = b.getAttribute("data-accion");
    var url = "/api/panel/usuarios/" + encodeURIComponent(nombre);
    if (accion === "estado") {
      var activar = b.getAttribute("data-activo") === "true";
      (activar ? Promise.resolve(true) : confirmar("Desactivar usuario", "El usuario " + nombre + " no podrá iniciar sesión hasta que se active de nuevo.", "Desactivar", true))
        .then(function (si) {
          if (!si) return;
          b.disabled = true;
          return postJSON(url + "/estado", { activo: activar }).then(function (r) {
            if (r.ok && r.datos && r.datos.ok) {
              mostrarUsr("ok", "Usuario " + nombre + (activar ? " activado" : " desactivado"), null, true);
              ejecutar("usuarios");
            } else {
              b.disabled = false;
              mostrarUsr("err", "No se pudo cambiar el estado de " + nombre, [el("ul", null, motivosDe(r).map(function (m) { return el("li", { text: m }); }))], true);
            }
          }, function (err) { b.disabled = false; errorRed(err); });
        });
    } else if (accion === "restablecer") {
      confirmar("Restablecer contraseña", "Se generará una contraseña temporal para " + nombre + ". Deberá cambiarla al ingresar.", "Restablecer", true)
        .then(function (si) {
          if (!si) return;
          b.disabled = true;
          return postJSON(url + "/restablecer", {}).then(function (r) {
            b.disabled = false;
            if (r.ok && r.datos && r.datos.ok && r.datos.clave_temporal) {
              mostrarUsr("ok", "Contraseña restablecida", [bloqueCredenciales("Nuevas credenciales de " + nombre, nombre, String(r.datos.clave_temporal),
                "Se pedirá cambiarla en el próximo ingreso. Esta contraseña se muestra una sola vez.")], true);
              ejecutar("usuarios");
            } else {
              mostrarUsr("err", "No se pudo restablecer la contraseña de " + nombre, [el("ul", null, motivosDe(r).map(function (m) { return el("li", { text: m }); }))], true);
            }
          }, function (err) { b.disabled = false; errorRed(err); });
        });
    }
  });

  /* Alta de usuarios */
  var formU = $("form-usuario");
  function nu(n) { return $("nu_" + n); }
  function nuVal(n) { var c = nu(n); return c ? String(c.value || "").trim() : ""; }
  var ETQ_NU = { username: "Usuario", nombre_completo: "Nombre completo", rol: "Rol", documento_id: "Documento", sede_id: "Sede", clave: "Contraseña inicial" };
  function opcionesSelect(sel, valores, etiqueta, vacio) {
    if (!sel) return;
    var actual = sel.value;
    vaciar(sel);
    if (vacio !== null) sel.appendChild(el("option", { value: "", text: vacio }));
    valores.forEach(function (v) { sel.appendChild(el("option", { value: String(v), text: etiqueta(v) })); });
    if (Array.prototype.some.call(sel.options, function (o) { return o.value === actual; })) sel.value = actual;
  }
  var firmaAlcance = "";
  function actualizarFormUsuario() {
    var det = $("nuevo-usuario");
    if (det) det.hidden = !ALCANCE.puede_gestionar;
    var f = JSON.stringify([ALCANCE.roles_asignables, ALCANCE.sedes_gestionables]);
    if (f === firmaAlcance) return;
    firmaAlcance = f;
    opcionesSelect(nu("rol"), arr(ALCANCE.roles_asignables), function (r) { return ROLES[r] || r; }, "— Seleccione —");
    var sedes = arr(ALCANCE.sedes_gestionables);
    opcionesSelect(nu("sede_id"), sedes, function (s) { var d = SEDES[String(s)]; return "Sede " + s + (d ? " · " + d.nombre : ""); }, sedes.length === 1 ? null : "Toda la red");
    ajustarRol();
  }
  function ajustarRol() {
    var rol = nuVal("rol");
    var ayudaDoc = nu("documento_ayuda"), ayudaSede = nu("sede_ayuda"), req = $("nu_doc_req");
    var docOblig = ["paciente", "medico", "admisionista"].indexOf(rol) >= 0;
    if (ayudaDoc) ayudaDoc.textContent = rol === "paciente" ? "Debe existir como paciente registrado." : (docOblig ? "Obligatorio." : (rol ? "Opcional." : "Obligatorio para paciente, médico y admisionista."));
    if (req) req.hidden = !!rol && !docOblig;
    var doc = nu("documento_id"); if (doc) { if (docOblig) doc.setAttribute("required", ""); else doc.removeAttribute("required"); }
    if (ayudaSede) ayudaSede.textContent = ["medico", "admisionista"].indexOf(rol) >= 0 ? "Obligatoria para este rol." : (rol ? "Opcional." : "Obligatoria para médico y admisionista.");
  }
  function errorNu(n) {
    var v = nuVal(n), rol = nuVal("rol");
    switch (n) {
      case "username": return !v ? "Escriba el usuario." : (RE_USUARIO.test(v) ? "" : "De 4 a 40 caracteres: minúsculas, números, punto o guion.");
      case "nombre_completo": return v ? "" : "Escriba el nombre completo.";
      case "rol": return v ? "" : "Seleccione el rol.";
      case "documento_id": return ["paciente", "medico", "admisionista"].indexOf(rol) >= 0 && !v ? "El documento es obligatorio para este rol." : (v && !/^\d{4,15}$/.test(v) ? "Solo dígitos, de 4 a 15." : "");
      case "sede_id": return ["medico", "admisionista"].indexOf(rol) >= 0 && !v ? "Seleccione la sede." : "";
      case "clave": return !v ? "" : (v.length < 8 ? "Mínimo 8 caracteres." : (/[A-Za-z]/.test(v) && /\d/.test(v) ? "" : "Combine letras y números."));
      default: return "";
    }
  }
  function mostrarErroresNu(lista) {
    var caja = $("nu-errores"); if (!caja) return;
    vaciar(caja);
    if (!lista.length) { caja.hidden = true; return; }
    var ul = el("ul");
    lista.forEach(function (er) {
      if (er.campo) {
        var a = el("a", { href: "#nu_" + er.campo, text: ETQ_NU[er.campo] + ": " + er.msg });
        a.addEventListener("click", function (ev) { ev.preventDefault(); var c = nu(er.campo); if (c) c.focus(); });
        ul.appendChild(el("li", null, [a]));
      } else ul.appendChild(el("li", { text: er.msg }));
    });
    caja.appendChild(ico("x"));
    caja.appendChild(el("strong", { text: lista.length === 1 ? "Corrija 1 dato:" : "Corrija " + lista.length + " datos:" }));
    caja.appendChild(ul);
    caja.hidden = false;
    caja.focus();
  }
  function ponerCreando(si) {
    var b = $("btn-crear-usuario"); if (!b) return;
    b.disabled = si || expirada;
    if (formU) formU.setAttribute("aria-busy", si ? "true" : "false");
    var sp = b.querySelector("span"); if (sp) sp.textContent = si ? "Creando…" : "Crear usuario";
  }
  if (formU) {
    var selRol = nu("rol");
    if (selRol) selRol.addEventListener("change", function () { ajustarRol(); });
    Object.keys(ETQ_NU).forEach(function (n) {
      var c = nu(n); if (!c) return;
      c.addEventListener("blur", function () {
        if (c.getAttribute("aria-invalid") === "true" || nuVal(n)) { var m = errorNu(n); if (m) c.setAttribute("aria-invalid", "true"); else c.removeAttribute("aria-invalid"); }
      });
    });
    formU.addEventListener("submit", function (e) {
      e.preventDefault();
      if (expirada) return;
      var errores = [];
      Object.keys(ETQ_NU).forEach(function (n) {
        var m = errorNu(n), c = nu(n);
        if (c) { if (m) c.setAttribute("aria-invalid", "true"); else c.removeAttribute("aria-invalid"); }
        if (m) errores.push({ campo: n, msg: m });
      });
      if (errores.length) { mostrarErroresNu(errores); anunciar("El formulario tiene " + errores.length + (errores.length === 1 ? " error." : " errores.")); return; }
      mostrarErroresNu([]);
      var cuerpo = { username: nuVal("username").toLowerCase(), nombre_completo: nuVal("nombre_completo"), rol: nuVal("rol"),
        documento_id: nuVal("documento_id") || null, sede_id: nuVal("sede_id") ? parseInt(nuVal("sede_id"), 10) : null };
      if (nuVal("clave")) cuerpo.clave = nuVal("clave");
      ponerCreando(true);
      postJSON("/api/panel/usuarios", cuerpo).then(function (r) {
        ponerCreando(false);
        var d = r.datos || {};
        if (r.ok && d.ok) {
          var u = d.usuario || {};
          var nombre = u.username || cuerpo.username;
          var extra = d.clave_temporal
            ? [bloqueCredenciales("Credenciales de acceso", nombre, String(d.clave_temporal))]
            : [el("p", { class: "resultado-sub", text: "Contraseña definida en el alta. Se pedirá cambiarla al primer ingreso." })];
          mostrarUsr("ok", "Usuario creado: " + nombre + " · " + (ROLES[u.rol || cuerpo.rol] || cuerpo.rol), extra, true);
          var sede = nuVal("sede_id");
          formU.reset();
          if (nu("sede_id")) nu("sede_id").value = sede;
          ajustarRol();
          pendienteU = nombre;
          ejecutar("usuarios");
        } else {
          mostrarErroresNu(motivosDe(r).map(function (m) { return { msg: m }; }));
          anunciar("No se pudo crear el usuario.");
        }
      }, function (err) { ponerCreando(false); errorRed(err); });
    });
  }
  if (ALCANCE && ALCANCE.cargado) { ALCANCE = normalizarAlcance(ALCANCE); actualizarFormUsuario(); }

  /* 9. Secciones (#resumen, #pacientes, …) --------------------------------- */
  var SECCIONES = ["resumen", "pacientes", "usuarios", "integracion", "fhir", "auditoria"];
  var TITULOS = { resumen: "Resumen", pacientes: "Pacientes", usuarios: "Usuarios", integracion: "Integración", fhir: "FHIR", auditoria: "Auditoría" };
  var tituloBase = document.title;
  function seccionDeHash() { var h = (location.hash || "").replace(/^#/, ""); return SECCIONES.indexOf(h) >= 0 ? h : null; }
  function mostrarSeccion(id, foco) {
    if (SECCIONES.indexOf(id) < 0) id = "resumen";
    var previa = seccionActual;
    seccionActual = id;
    SECCIONES.forEach(function (s) { var nodo = $(s); if (nodo) nodo.hidden = s !== id; });
    Array.prototype.forEach.call(document.querySelectorAll(".consola-nav a[data-seccion]"), function (a) {
      if (a.getAttribute("data-seccion") === id) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    });
    var tu = document.querySelector('.nav a[data-nav="usuarios"]'), tp = document.querySelector('.nav a[data-nav="panel"]');
    if (tu) { if (id === "usuarios") tu.setAttribute("aria-current", "page"); else tu.removeAttribute("aria-current"); }
    if (tp) { if (id !== "usuarios") tp.setAttribute("aria-current", "page"); else tp.removeAttribute("aria-current"); }
    document.title = TITULOS[id] + " · " + tituloBase;
    if (foco) {
      var h = $("t-" + id);
      var consola = document.querySelector(".consola");
      if (consola && consola.getBoundingClientRect().top < 0) {
        try { window.scrollTo({ top: window.pageYOffset + consola.getBoundingClientRect().top - 8, behavior: "auto" }); } catch (e) { /* sin soporte */ }
      }
      if (h) h.focus({ preventScroll: true });
    }
    var fu = fuentes.usuarios;
    if (id === "usuarios" && previa !== "usuarios") ejecutar("usuarios");
    else if (id !== "usuarios") {
      clearTimeout(fu.timer); fu.timer = null;
      if (fu.errores) { fu.errores = 0; recuperado(); }
    }
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("a[data-seccion]") : null;
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
    e.preventDefault();
    var id = a.getAttribute("data-seccion");
    if (seccionDeHash() !== id) { try { history.pushState(null, "", "#" + id); } catch (er) { location.hash = id; return; } }
    mostrarSeccion(id, true);
  });
  window.addEventListener("hashchange", function () { mostrarSeccion(seccionDeHash() || "resumen", true); });
  window.addEventListener("popstate", function () { var s = seccionDeHash() || "resumen"; if (s !== seccionActual) mostrarSeccion(s, true); });
  mostrarSeccion(seccionDeHash() || "resumen", false);
  if (seccionDeHash()) {
    var arriba = function () { try { window.scrollTo(0, 0); } catch (e) { /* sin soporte */ } };
    arriba();
    if (document.readyState !== "complete") window.addEventListener("load", function () { setTimeout(arriba, 0); }, { once: true });
  }

  programar("resumen");
  programar("pacientes");
})();
