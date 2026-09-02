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
});
