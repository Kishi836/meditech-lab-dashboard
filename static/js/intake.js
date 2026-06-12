/* Meditech Lab 2.5 — Intake panel behaviour
   Two front-desk workflows, both entering REAL data via HL7 documents:
   - Register Patient → POST /api/intake/patient (ADT^A04)
   - Record Result   → POST /api/intake/result  (ORU^R01)
   Each form keeps a live document preview (debounced POST /api/intake/preview)
   and replays the staged backend result on a compact PipeSVG strip. Field
   errors from the 400 {errors} response land under their inputs.

   Exposes window.IntakePanel = { openRegister(), openResult(patientId) } so
   the Patients panel can deep-link in; on success it calls
   window.PatientsPanel.refresh()/open(id) to sync the registry view. */

(function () {
  "use strict";

  const PREVIEW_DEBOUNCE_MS = 250;

  let pipes = { register: null, result: null };
  let catalog = [];          // /api/catalog/tests entries
  let previewTimers = {};

  function el(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value == null ? "" : value);
    return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function toast(message, kind) {
    if (window.showToast) {
      window.showToast(message, kind);
    }
  }

  function setStatus(which, message, kind) {
    const node = el(`intake-${which}-status`);
    node.textContent = message || "";
    node.className = "intake-status" + (kind ? ` intake-status-${kind}` : "");
  }

  // ───────────── form switch ─────────────

  function showForm(which) {
    document.querySelectorAll(".intake-switch-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-form") === which);
    });
    el("intake-card-register").hidden = which !== "register";
    el("intake-card-result").hidden = which !== "result";
  }

  // ───────────── field errors ─────────────

  function clearErrors(form) {
    form.querySelectorAll(".intake-error").forEach((node) => {
      node.textContent = "";
    });
  }

  function showErrors(form, errors) {
    Object.entries(errors || {}).forEach(([field, message]) => {
      const node = form.querySelector(`.intake-error[data-field="${field}"]`);
      if (node) node.textContent = message;
    });
  }

  // ───────────── live previews ─────────────

  function schedulePreview(kind) {
    clearTimeout(previewTimers[kind]);
    previewTimers[kind] = setTimeout(() => updatePreview(kind), PREVIEW_DEBOUNCE_MS);
  }

  function registerPayload() {
    return {
      full_name: el("intake-reg-name").value,
      dob: el("intake-reg-dob").value,
      gender: el("intake-reg-gender").value,
      blood_type: el("intake-reg-blood").value,
      phone: el("intake-reg-phone").value,
      city: el("intake-reg-city").value,
    };
  }

  function resultPayload() {
    return {
      patient_id: el("intake-res-patient").value,
      loinc_code: el("intake-res-test").value,
      value: el("intake-res-value").value,
      obs_date: el("intake-res-date").value,
    };
  }

  function updatePreview(kind) {
    const body = kind === "register"
      ? { kind: "patient", ...registerPayload() }
      : { kind: "result", ...resultPayload() };

    fetch("/api/intake/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((res) => res.json())
      .then((data) => {
        el(`intake-${kind}-preview`).textContent = data.hl7
          ? data.hl7.split("\r").join("\n")
          : data.error || "—";
      })
      .catch(() => {
        el(`intake-${kind}-preview`).textContent = "Couldn't build a preview.";
      });
  }

  // ───────────── register patient ─────────────

  function submitRegister(evt) {
    evt.preventDefault();
    const form = el("intake-register-form");
    const btn = el("intake-register-send");
    clearErrors(form);
    btn.disabled = true;
    setStatus("register", "Sending ADT^A04…", "");
    pipes.register.reset();

    fetch("/api/intake/patient", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(registerPayload()),
    })
      .then((res) => res.json().then((data) => ({ status: res.status, data })))
      .then(({ status, data }) => {
        if (status === 400) {
          showErrors(form, data.errors);
          setStatus("register", "Fix the highlighted fields.", "error");
          return null;
        }
        if (status !== 200) throw new Error(data.error || `HTTP ${status}`);

        el("intake-register-preview").textContent =
          data.hl7.split("\r").join("\n");
        return pipes.register.play(data.stages).then(() => {
          const errored = data.stages.some((s) => s.status === "error");
          if (errored) {
            setStatus("register", `Sent ${data.msg_id} with errors — see the pipeline.`, "error");
            return;
          }
          setStatus("register",
            `${data.patient_id} (${data.mrn}) registered ✓`, "ok");
          toast(`Patient registered — ${data.patient_id} · ${data.mrn}`, "ok");
          form.reset();
          schedulePreview("register");
          if (window.PatientsPanel) window.PatientsPanel.refresh();
          loadPatientsForResult(); // the new patient is now selectable
        });
      })
      .catch((err) => setStatus("register", `Failed: ${err.message}`, "error"))
      .finally(() => {
        btn.disabled = false;
      });
  }

  // ───────────── record result ─────────────

  function catalogEntry(loinc) {
    return catalog.find((t) => t.loinc_code === loinc) || null;
  }

  function refStr(entry) {
    if (!entry) return "";
    const low = entry.ref_low, high = entry.ref_high;
    if (low != null && high != null) return `${low}–${high}`;
    if (high != null) return `< ${high}`;
    if (low != null) return `≥ ${low}`;
    return "—";
  }

  function updateTestInfo() {
    const entry = catalogEntry(el("intake-res-test").value);
    el("intake-res-unit").textContent = entry ? entry.unit : "";
    el("intake-res-ref").textContent = entry
      ? `Reference: ${refStr(entry)} ${entry.unit}` +
        (entry.critical_dir
          ? ` · critical when ${entry.critical_dir === "high" ? ">" : "<"} ${entry.critical_at}`
          : "")
      : "";
    updateFlagLine();
  }

  function updateFlagLine() {
    const node = el("intake-res-flagline");
    const entry = catalogEntry(el("intake-res-test").value);
    const value = parseFloat(el("intake-res-value").value);
    if (!entry || isNaN(value)) {
      node.textContent = "";
      node.className = "intake-flagline";
      return;
    }
    const critical = entry.critical_dir &&
      (entry.critical_dir === "high" ? value > entry.critical_at
                                     : value < entry.critical_at);
    const high = entry.ref_high != null && value > entry.ref_high;
    const low = entry.ref_low != null && value < entry.ref_low;
    if (critical) {
      node.textContent = `⚠ ${value} ${entry.unit} crosses the critical threshold — this will raise an alert.`;
      node.className = "intake-flagline intake-flagline-critical";
    } else if (high || low) {
      node.textContent = `${value} ${entry.unit} is ${high ? "above" : "below"} the reference range.`;
      node.className = "intake-flagline intake-flagline-abnormal";
    } else {
      node.textContent = `${value} ${entry.unit} is within the reference range.`;
      node.className = "intake-flagline intake-flagline-normal";
    }
  }

  function submitResult(evt) {
    evt.preventDefault();
    const form = el("intake-result-form");
    const btn = el("intake-result-send");
    clearErrors(form);
    btn.disabled = true;
    setStatus("result", "Sending ORU^R01…", "");
    pipes.result.reset();

    fetch("/api/intake/result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(resultPayload()),
    })
      .then((res) => res.json().then((data) => ({ status: res.status, data })))
      .then(({ status, data }) => {
        if (status === 400) {
          showErrors(form, data.errors);
          setStatus("result", "Fix the highlighted fields.", "error");
          return null;
        }
        if (status !== 200) throw new Error(data.error || `HTTP ${status}`);

        el("intake-result-preview").textContent =
          data.hl7.split("\r").join("\n");
        return pipes.result.play(data.stages).then(() => {
          const errored = data.stages.some((s) => s.status === "error");
          if (errored) {
            setStatus("result", `Sent ${data.msg_id} with errors — see the pipeline.`, "error");
            return;
          }
          const obs = data.obs;
          if (data.critical) {
            setStatus("result",
              `${obs.display_name} ${obs.value} ${obs.unit} saved — ⚠ CRITICAL value.`, "error");
            toast(`⚠ Critical ${obs.display_name}: ${obs.value} ${obs.unit}`, "error");
          } else {
            setStatus("result",
              `${obs.display_name} ${obs.value} ${obs.unit} saved ✓ (${obs.flag})`, "ok");
            toast(`Result saved — ${obs.display_name} ${obs.value} ${obs.unit}`, "ok");
          }
          el("intake-res-value").value = "";
          updateFlagLine();
          schedulePreview("result");
          if (window.PatientsPanel) window.PatientsPanel.refresh();
        });
      })
      .catch((err) => setStatus("result", `Failed: ${err.message}`, "error"))
      .finally(() => {
        btn.disabled = false;
      });
  }

  // ───────────── data loading ─────────────

  function loadPatientsForResult(selectId) {
    return fetch("/api/patients")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((patients) => {
        const sel = el("intake-res-patient");
        const keep = selectId || sel.value;
        sel.innerHTML = "";
        (patients || []).forEach((p) => {
          const opt = document.createElement("option");
          opt.value = p.patient_id;
          opt.textContent = `${p.full_name} (${p.patient_id})`;
          sel.appendChild(opt);
        });
        if (keep) sel.value = keep;
        if (!sel.value && sel.options.length) sel.selectedIndex = 0;
      })
      .catch(() => {
        setStatus("result", "Couldn't reach the database — is Postgres running?", "error");
      });
  }

  function loadCatalog() {
    return fetch("/api/catalog/tests")
      .then((res) => res.json())
      .then((tests) => {
        catalog = tests || [];
        const sel = el("intake-res-test");
        sel.innerHTML = "";
        catalog.forEach((t) => {
          const opt = document.createElement("option");
          opt.value = t.loinc_code;
          opt.textContent = `${t.display_name} (${t.loinc_code})`;
          sel.appendChild(opt);
        });
        updateTestInfo();
      })
      .catch(() => {});
  }

  // ───────────── public hooks (used by the Patients panel) ─────────────

  window.IntakePanel = {
    openRegister() {
      showForm("register");
      schedulePreview("register");
    },
    openResult(patientId) {
      showForm("result");
      loadPatientsForResult(patientId).then(() => schedulePreview("result"));
    },
  };

  // ───────────── lifecycle ─────────────

  function init() {
    pipes.register = PipeSVG.mount(el("intake-register-pipe"), { compact: true });
    pipes.result = PipeSVG.mount(el("intake-result-pipe"), { compact: true });

    document.querySelectorAll(".intake-switch-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        showForm(btn.getAttribute("data-form"));
      });
    });

    el("intake-register-form").addEventListener("submit", submitRegister);
    el("intake-result-form").addEventListener("submit", submitResult);

    // Live previews track every keystroke / selection change.
    ["intake-reg-name", "intake-reg-dob", "intake-reg-gender", "intake-reg-blood",
     "intake-reg-phone", "intake-reg-city"].forEach((id) => {
      el(id).addEventListener("input", () => schedulePreview("register"));
    });
    ["intake-res-patient", "intake-res-test", "intake-res-value",
     "intake-res-date"].forEach((id) => {
      el(id).addEventListener("input", () => schedulePreview("result"));
    });
    el("intake-res-test").addEventListener("input", updateTestInfo);
    el("intake-res-value").addEventListener("input", updateFlagLine);

    const navBtn = document.querySelector('.nav-item[data-panel="intake"]');
    if (navBtn) {
      navBtn.addEventListener("click", () => {
        loadPatientsForResult();
      });
    }

    loadCatalog();
    loadPatientsForResult();
    schedulePreview("register");
  }

  document.addEventListener("DOMContentLoaded", init);
})();
