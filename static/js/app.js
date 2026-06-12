/* Meditech Lab 2.0 — dashboard shell behaviour
   - Switches the visible content panel when a sidebar nav item is clicked.
   - Polls /api/health every few seconds and reflects the result in the
     two status dots (Postgres, Elasticsearch).
   - window.showToast(message, kind): transient notifications, used by the
     Intake and Pipeline modules ("ok" green, "error" red, default blue). */

(function () {
  "use strict";

  const HEALTH_POLL_MS = 5000;
  const TOAST_MS = 4200;

  // ───────────── toasts ─────────────

  function showToast(message, kind) {
    let host = document.getElementById("toast-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "toast-host";
      host.className = "toast-host";
      document.body.appendChild(host);
    }
    const toast = document.createElement("div");
    toast.className = "toast" + (kind ? ` toast-${kind}` : "");
    toast.setAttribute("role", "status");
    toast.textContent = message;
    host.appendChild(toast);
    setTimeout(() => {
      toast.classList.add("toast-out");
      setTimeout(() => toast.remove(), 400);
    }, TOAST_MS);
  }

  window.showToast = showToast;

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
