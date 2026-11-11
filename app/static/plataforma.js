/* Plataforma de Interoperabilidad Clínica · mejoras progresivas.
   Sin este archivo la interfaz sigue funcionando: solo añade el botón «Copiar»
   a los sellos SHA-256 y convierte los bloques [data-tabs] en pestañas accesibles. */
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  /* 0. Menú de la cuenta: se cierra con Escape o al pulsar fuera ------------- */
  document.querySelectorAll(".usuario-menu").forEach(function (menu) {
    var sum = menu.querySelector("summary");
    document.addEventListener("click", function (e) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
    menu.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && menu.open) { menu.open = false; if (sum) sum.focus(); }
    });
  });

  /* 1. Copiar sellos ------------------------------------------------------- */
  function copiar(texto) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(texto);
    }
    return new Promise(function (ok, falla) {
      var t = document.createElement("textarea");
      t.value = texto; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
      document.body.appendChild(t); t.select();
      try { document.execCommand("copy") ? ok() : falla(); } catch (e) { falla(e); }
      document.body.removeChild(t);
    });
  }

  document.querySelectorAll("[data-copiar]").forEach(function (chip) {
    var valor = chip.getAttribute("data-copiar");
    if (!valor) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn-copiar";
    b.textContent = "Copiar";
    var etq = chip.getAttribute("data-copiar-etq") || "código de verificación";
    b.setAttribute("aria-label", "Copiar " + etq + (valor.length > 16 ? " " + valor.slice(0, 12) + "…" : ""));
    b.addEventListener("click", function () {
      copiar(valor).then(function () {
        b.textContent = "Copiado ✓"; b.classList.add("hecho");
        setTimeout(function () { b.textContent = "Copiar"; b.classList.remove("hecho"); }, 1800);
      }, function () { b.textContent = "Selecciónelo"; });
    });
    chip.appendChild(b);
    chip.classList.remove("corto");
  });

  /* 2. Pestañas accesibles (patrón WAI-ARIA tabs) -------------------------- */
  document.querySelectorAll("[data-tabs]").forEach(function (cont, n) {
    var paneles = Array.prototype.slice.call(cont.querySelectorAll(":scope > [data-tab]"));
    if (paneles.length < 2) return;
    var lista = document.createElement("div");
    lista.className = "tabs-lista";
    lista.setAttribute("role", "tablist");
    lista.setAttribute("aria-label", cont.getAttribute("data-tabs") || "Pestañas");
    var botones = paneles.map(function (p, i) {
      var id = p.id || ("panel-" + n + "-" + i);
      p.id = id;
      var b = document.createElement("button");
      b.type = "button";
      b.id = id + "-tab";
      b.setAttribute("role", "tab");
      b.setAttribute("aria-controls", id);
      b.innerHTML = p.getAttribute("data-tab-ico") || "";
      b.appendChild(document.createTextNode(p.getAttribute("data-tab")));
      p.setAttribute("role", "tabpanel");
      p.setAttribute("aria-labelledby", b.id);
      p.setAttribute("tabindex", "0");
      lista.appendChild(b);
      return b;
    });
    function activar(i, foco) {
      botones.forEach(function (b, j) {
        var on = i === j;
        b.setAttribute("aria-selected", on ? "true" : "false");
        b.tabIndex = on ? 0 : -1;
        paneles[j].hidden = !on;
      });
      if (foco) botones[i].focus();
    }
    botones.forEach(function (b, i) {
      b.addEventListener("click", function () { activar(i, false); });
      b.addEventListener("keydown", function (e) {
        var k = e.key, j = null;
        if (k === "ArrowRight") j = (i + 1) % botones.length;
        else if (k === "ArrowLeft") j = (i - 1 + botones.length) % botones.length;
        else if (k === "Home") j = 0;
        else if (k === "End") j = botones.length - 1;
        if (j !== null) { e.preventDefault(); activar(j, true); }
      });
    });
    cont.insertBefore(lista, paneles[0]);
    cont.classList.add("tabs-activas");
    activar(0, false);
  });
})();
