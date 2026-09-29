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
