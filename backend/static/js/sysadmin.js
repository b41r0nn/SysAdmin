document.addEventListener("DOMContentLoaded", function () {
  const sidebar = document.querySelector(".sidebar");
  if (!sidebar) {
    // continue even without sidebar so auth view enhancements run
  }

  if (sidebar) {
    const links = sidebar.querySelectorAll(".nav-link");
    links.forEach(function (link) {
      link.addEventListener("click", function () {
        links.forEach(function (item) {
          item.classList.remove("active");
        });
        link.classList.add("active");
      });
    });
  }

  document.querySelectorAll(".sa-stat-card").forEach(function (card) {
    card.addEventListener("mouseenter", function () {
      card.style.transform = "translateY(-4px)";
      card.style.boxShadow = "0 10px 25px rgba(15, 23, 42, 0.12)";
    });
    card.addEventListener("mouseleave", function () {
      card.style.transform = "translateY(0)";
      card.style.boxShadow = "0 1px 3px rgba(15, 23, 42, 0.08)";
    });
  });

  document.querySelectorAll(".form-control, .form-select").forEach(function (input) {
    input.addEventListener("focus", function () {
      if (input.parentElement) {
        input.parentElement.classList.add("focused");
      }
    });
    input.addEventListener("blur", function () {
      if (input.parentElement) {
        input.parentElement.classList.remove("focused");
      }
    });
  });

  initFiltroActivos();
  initAvisosHtmx();
});

/**
 * Filtra en cliente el <select> de activos del panel de vinculación de Yule.
 *
 * El select se renderiza con todos los activos porque es lo que se envía al
 * servidor y así el formulario sigue funcionando sin JavaScript. Con cientos de
 * activos, buscar a mano en la lista es inviable, así que el input de texto
 * esconde las <option> que no coinciden en vez de reconstruirlas: conservar los
 * nodos mantiene el valor seleccionado y no pierde foco mientras se escribe.
 */
function initFiltroActivos() {
  document.querySelectorAll("[data-filtro-activos]").forEach(function (filtro) {
    const contenedor = filtro.closest("form") || filtro.parentElement;
    const select = contenedor && contenedor.querySelector("select[name='activo']");
    if (!select) {
      return;
    }
    const vacio = filtro.placeholder.trim();

    function aplicar() {
      const texto = filtro.value.trim().toLowerCase();
      let visibles = 0;
      Array.prototype.forEach.call(select.options, function (opcion) {
        if (!opcion.value) {
          return;
        }
        const coincide = !texto || opcion.textContent.toLowerCase().indexOf(texto) !== -1;
        opcion.hidden = !coincide;
        opcion.disabled = !coincide;
        if (coincide) {
          visibles += 1;
        }
      });
      filtro.setAttribute(
        "placeholder",
        visibles ? vacio : "Sin coincidencias: revisa el serial"
      );
    }

    filtro.addEventListener("input", aplicar);
    filtro.addEventListener("search", aplicar);
    aplicar();
  });
}

/* ─── Avisos de los errores de HTMX ──────────────────────────────────────────
 *
 * Un cambio por HTMX que el servidor rechaza es invisible sin esto: con un 4xx
 * HTMX no intercambia nada, así que el interruptor o el <select> se quedan
 * mostrando el valor que el usuario acaba de poner aunque no se haya guardado
 * nada. Pasa con un 403 (sin permiso, o sesión caducada: el caso universal, a
 * los 30 min de inactividad), con un 400 (un rechazo legítimo de la vista, como
 * intentar apagar un módulo esencial) y con un 404 (alguien borró la fila por
 * consola con la pantalla abierta).
 */

const SELECTOR_CONTROLES_HTMX =
  "input[hx-post], select[hx-post], input[hx-get], select[hx-get]";

/**
 * Apunta en cada control el valor que el servidor tiene de verdad.
 *
 * Hace falta recordarlo al pintar: cuando salta el error, el control ya tiene
 * el valor que el usuario acaba de poner, así que leerlo entonces no sirve para
 * volver atrás. Se vuelve a apuntar en cada intercambio de HTMX, porque un
 * guardado correcto devuelve el control ya repintado por el servidor.
 */
function recordarValorReal(raiz) {
  if (!raiz || !raiz.querySelectorAll) {
    return;
  }
  const controles = [];
  if (raiz.matches && raiz.matches(SELECTOR_CONTROLES_HTMX)) {
    controles.push(raiz);
  }
  raiz.querySelectorAll(SELECTOR_CONTROLES_HTMX).forEach(function (control) {
    controles.push(control);
  });
  controles.forEach(function (control) {
    control.dataset.valorReal = esCasilla(control)
      ? control.checked
        ? "1"
        : "0"
      : control.value;
  });
}

function esCasilla(control) {
  return control.type === "checkbox" || control.type === "radio";
}

function restaurarValorReal(control) {
  if (!control || !control.dataset || control.dataset.valorReal === undefined) {
    return;
  }
  if (esCasilla(control)) {
    control.checked = control.dataset.valorReal === "1";
  } else {
    control.value = control.dataset.valorReal;
  }
}

/**
 * El motivo que se le muestra al usuario.
 *
 * El 403 del decorador de permisos y los 400 de las vistas mandan el motivo en
 * el cuerpo, en español y en texto plano: se muestra tal cual. Un 404 (o un
 * 500) responde una página entera de Django, que no sirve de aviso, así que
 * ahí se pone un texto propio.
 */
function mensajeDelErrorHtmx(xhr) {
  const cuerpo = xhr && xhr.responseText ? xhr.responseText.trim() : "";
  if (cuerpo && cuerpo.length <= 300 && cuerpo.indexOf("<") === -1) {
    return cuerpo;
  }
  if (xhr && xhr.status === 404) {
    return "Lo que intentabas cambiar ya no existe: alguien lo borró. Recarga la página.";
  }
  return "No se pudo guardar el cambio. Recarga la página y vuelve a intentarlo.";
}

/** Pinta el aviso con el mismo patrón de alertas que usa base.html. */
function avisarEnPantalla(texto) {
  const contenedor = document.querySelector("main.sa-content") || document.body;
  contenedor.querySelectorAll("[data-aviso-htmx]").forEach(function (viejo) {
    viejo.remove();
  });
  const aviso = document.createElement("div");
  aviso.className = "alert alert-danger alert-dismissible fade show";
  aviso.setAttribute("role", "alert");
  aviso.setAttribute("data-aviso-htmx", "");
  // textContent y no innerHTML: el motivo viene del servidor y se muestra como
  // texto, nunca como HTML.
  aviso.textContent = texto;
  const cerrar = document.createElement("button");
  cerrar.type = "button";
  cerrar.className = "btn-close";
  cerrar.setAttribute("data-bs-dismiss", "alert");
  cerrar.setAttribute("aria-label", "Cerrar");
  aviso.appendChild(cerrar);
  contenedor.insertBefore(aviso, contenedor.firstChild);
  aviso.scrollIntoView({ block: "nearest" });
}

function initAvisosHtmx() {
  const cuerpo = document.body;
  if (!cuerpo) {
    return;
  }
  recordarValorReal(cuerpo);
  cuerpo.addEventListener("htmx:load", function (evento) {
    recordarValorReal(evento.detail ? evento.detail.elt : null);
  });
  cuerpo.addEventListener("htmx:responseError", function (evento) {
    const detalle = evento.detail || {};
    restaurarValorReal(detalle.elt);
    avisarEnPantalla(mensajeDelErrorHtmx(detalle.xhr));
  });
}
