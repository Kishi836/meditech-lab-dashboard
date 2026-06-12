/* Meditech Lab 2.0 — dashboard shell behaviour
   - Switches the visible content panel when a sidebar nav item is clicked.
   - Polls /api/health every few seconds and reflects the result in the
     two status dots (Postgres, Elasticsearch). */

(function () {
  "use strict";

  const HEALTH_POLL_MS = 5000;

  function activatePanel(target) {
    document.querySelectorAll(".nav-item").forEach((n) => {
      n.classList.toggle("active", n.getAttribute("data-panel") === target);
    });
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === `panel-${target}`);
    });
  }

  function initNav() {
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.addEventListener("click", () => {
        activatePanel(item.getAttribute("data-panel"));
      });
    });
  }

  // Programmatic navigation for cross-panel links (Patients ⇄ Intake).
  window.AppNav = { go: activatePanel };

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
