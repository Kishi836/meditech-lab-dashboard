/* Meditech Lab 2.0 — dashboard shell behaviour
   - Switches the visible content panel when a sidebar nav item is clicked.
   - Polls /api/health every few seconds and reflects the result in the
     two status dots (Postgres, Elasticsearch). */

(function () {
  "use strict";

  const HEALTH_POLL_MS = 5000;

  function initNav() {
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach((item) => {
      item.addEventListener("click", () => {
        const target = item.getAttribute("data-panel");

        navItems.forEach((n) => n.classList.remove("active"));
        item.classList.add("active");

        document.querySelectorAll(".panel").forEach((panel) => {
          panel.classList.toggle("active", panel.id === `panel-${target}`);
        });
      });
    });
  }

  function setDot(el, state) {
    // state: true -> ok, false -> down, "disabled" -> disabled/skipped
    el.classList.remove("ok", "down", "disabled");
    if (state === true) {
      el.classList.add("ok");
    } else if (state === false) {
      el.classList.add("down");
    } else {
      el.classList.add("disabled");
    }
  }

  function pollHealth() {
    const dotPostgres = document.getElementById("dot-postgres");
    const dotEs = document.getElementById("dot-es");

    fetch("/api/health")
      .then((res) => res.json())
      .then((data) => {
        setDot(dotPostgres, data.postgres);
        setDot(dotEs, data.es);
      })
      .catch(() => {
        setDot(dotPostgres, false);
        setDot(dotEs, false);
      });
  }

  function initHealthPoll() {
    pollHealth();
    setInterval(pollHealth, HEALTH_POLL_MS);
  }

  document.addEventListener("DOMContentLoaded", () => {
    initNav();
    initHealthPoll();
  });
})();
