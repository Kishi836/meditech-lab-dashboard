/* Meditech Lab 2.0 — Pipeline panel behaviour
   - Compose: pick a patient + HL7 message type → live preview (POST
     /api/hl7/preview). Send (POST /api/hl7/send) runs the six-stage hybrid
     pipeline and the diagram animates each stage in sequence using the
     returned stages[] (green=ok, grey=skipped, red=error) with ms + detail.
   - Live feed (GET /api/pipeline/feed) and Chart.js analytics (diagnoses by
     dept, messages sent, critical values) refresh after every send/reset and
     whenever the Pipeline tab is opened.
   - Reset (GET /api/pipeline/reset) clears the pipeline-created rows + files.
   - Degrades gracefully: a failed fetch shows a friendly status, never a
     stack trace; charts are skipped if Chart.js didn't load. */

(function () {
  "use strict";

  // Stage metadata — order matches the backend pipeline.
  const STAGES = [
    { key: "build",         label: "Build",         sub: "HL7 v2.5", kind: "real" },
    { key: "nifi_route",    label: "NiFi",          sub: "route",    kind: "sim" },
    { key: "postgres",      label: "Postgres",      sub: "insert",   kind: "real" },
    { key: "elasticsearch", label: "Elasticsearch", sub: "index",    kind: "real" },
    { key: "kibana",        label: "Kibana",        sub: "charts",   kind: "sim" },
    { key: "minio",         label: "MinIO",         sub: "archive",  kind: "sim" },
  ];

  const STAGE_STEP_MS = 240; // stagger between stages lighting up

  const charts = {};         // {dept, msgs} live Chart instances
  let patientsLoaded = false;

  function el(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value == null ? "" : value);
    return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function setStatus(message, kind) {
    const node = el("pipeline-status");
    node.textContent = message || "";
    node.className = "pipeline-status" + (kind ? ` pipeline-status-${kind}` : "");
  }

  // ───────────── compose: patients + live preview ─────────────

  function loadPatients() {
    return fetch("/api/patients")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((patients) => {
        const sel = el("pipeline-patient");
        sel.innerHTML = "";
        (patients || []).forEach((p) => {
          const opt = document.createElement("option");
          opt.value = p.patient_id;
          opt.textContent = `${p.full_name} (${p.patient_id})`;
          sel.appendChild(opt);
        });
        patientsLoaded = true;
        updatePreview();
      })
      .catch(() => {
        setStatus("Couldn't reach the database — is Postgres running?", "error");
        el("pipeline-preview").textContent =
          "Database unavailable — start Postgres and reopen this tab.";
      });
  }

  function selection() {
    return {
      patient_id: el("pipeline-patient").value,
      msg_type: el("pipeline-msgtype").value,
    };
  }

  function updatePreview() {
    const sel = selection();
    if (!sel.patient_id) return;
    fetch("/api/hl7/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sel),
    })
      .then((res) => res.json())
      .then((data) => {
        // HL7 segments are \r-separated; show one per line.
        el("pipeline-preview").textContent = data.hl7
          ? data.hl7.split("\r").join("\n")
          : data.error || "—";
      })
      .catch(() => {
        el("pipeline-preview").textContent = "Couldn't build a preview.";
      });
  }

  // ───────────── stage diagram ─────────────

  function renderStages() {
    const host = el("pipeline-stages");
    host.innerHTML = "";
    STAGES.forEach((s, idx) => {
      if (idx > 0) {
        const arrow = document.createElement("div");
        arrow.className = "pipeline-arrow";
        arrow.innerHTML = "&#8594;";
        host.appendChild(arrow);
      }
      const card = document.createElement("div");
      card.className = "pipeline-stage";
      card.id = `pipeline-stage-${s.key}`;
      card.innerHTML = `
        <div class="pipeline-stage-kind pipeline-stage-kind-${s.kind}">${s.kind === "real" ? "real" : "sim"}</div>
        <div class="pipeline-stage-name">${escapeHtml(s.label)}</div>
        <div class="pipeline-stage-sub muted">${escapeHtml(s.sub)}</div>
        <div class="pipeline-stage-detail" id="pipeline-stage-detail-${s.key}"></div>`;
      host.appendChild(card);
    });
  }

  function resetStages() {
    STAGES.forEach((s) => {
      const card = el(`pipeline-stage-${s.key}`);
      if (card) card.className = "pipeline-stage";
      const detail = el(`pipeline-stage-detail-${s.key}`);
      if (detail) detail.textContent = "";
    });
  }

  function paintStage(stage) {
    const card = el(`pipeline-stage-${stage.stage}`);
    if (card) card.className = `pipeline-stage pipeline-stage-${stage.status}`;
    const detail = el(`pipeline-stage-detail-${stage.stage}`);
    if (detail) detail.textContent = `${stage.detail} · ${stage.ms}ms`;
  }

  function animateStages(stages) {
    return new Promise((resolve) => {
      stages.forEach((stage, i) => {
        setTimeout(() => {
          paintStage(stage);
          if (i === stages.length - 1) resolve();
        }, i * STAGE_STEP_MS);
      });
      if (!stages.length) resolve();
    });
  }

  // ───────────── send / reset ─────────────

  function send() {
    const btn = el("pipeline-send");
    btn.disabled = true;
    setStatus("Sending…", "");
    resetStages();

    fetch("/api/hl7/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(selection()),
    })
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.error || "send failed");
        el("pipeline-preview").textContent = data.hl7
          ? data.hl7.split("\r").join("\n")
          : "";
        return animateStages(data.stages).then(() => {
          const errored = data.stages.some((s) => s.status === "error");
          setStatus(
            errored
              ? `Sent ${data.msg_id} with errors — see stages above.`
              : `Sent ${data.msg_id} — row written, archived ✓`,
            errored ? "error" : "ok"
          );
          refresh();
        });
      })
      .catch((err) => setStatus(`Send failed: ${err.message}`, "error"))
      .finally(() => {
        btn.disabled = false;
      });
  }

  function reset() {
    const btn = el("pipeline-reset");
    btn.disabled = true;
    setStatus("Resetting…", "");
    fetch("/api/pipeline/reset")
      .then((res) => res.json())
      .then((data) => {
        resetStages();
        setStatus(
          `Reset — removed pipeline rows + ${data.archive_files_removed} archive file(s).`,
          "ok"
        );
        refresh();
        updatePreview();
      })
      .catch(() => setStatus("Reset failed — is Postgres running?", "error"))
      .finally(() => {
        btn.disabled = false;
      });
  }

  // ───────────── live feed ─────────────

  function loadFeed() {
    fetch("/api/pipeline/feed")
      .then((res) => res.json())
      .then((entries) => renderFeed(entries))
      .catch(() => {
        /* leave existing feed in place on a transient failure */
      });
  }

  function renderFeed(entries) {
    const list = el("pipeline-feed");
    if (!entries || !entries.length) {
      list.innerHTML = `<li class="pipeline-feed-empty muted">No messages sent yet.</li>`;
      return;
    }
    list.innerHTML = entries
      .map(
        (e) => `
        <li class="pipeline-feed-item">
          <span class="pipeline-feed-dot pipeline-feed-dot-${escapeHtml(e.status)}"></span>
          <span class="pipeline-feed-type">${escapeHtml(e.msg_type)}</span>
          <span class="pipeline-feed-patient">${escapeHtml(e.patient)}</span>
          <span class="pipeline-feed-table muted">&rarr; ${escapeHtml(e.table || "—")}</span>
          <span class="pipeline-feed-time muted">${escapeHtml((e.ts || "").replace("T", " "))}</span>
        </li>`
      )
      .join("");
  }

  // ───────────── analytics ─────────────

  function loadAnalytics() {
    loadCritical();
    if (typeof Chart === "undefined") return; // charts optional
    loadDeptChart();
    loadMsgChart();
  }

  function barChart(canvasId, key, labels, values, color) {
    const canvas = el(canvasId);
    if (!canvas) return;
    if (charts[key]) {
      charts[key].destroy();
    }
    charts[key] = new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: color,
            borderColor: color,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          y: {
            beginAtZero: true,
            ticks: { color: "#8b949e", precision: 0 },
            grid: { color: "#30363d" },
          },
        },
      },
    });
  }

  function loadDeptChart() {
    fetch("/api/analytics/conditions_by_dept")
      .then((res) => res.json())
      .then((rows) => {
        barChart(
          "pipeline-chart-dept",
          "dept",
          rows.map((r) => r.department),
          rows.map((r) => r.count),
          "#58a6ff"
        );
      })
      .catch(() => {});
  }

  function loadMsgChart() {
    fetch("/api/analytics/message_counts")
      .then((res) => res.json())
      .then((rows) => {
        barChart(
          "pipeline-chart-msgs",
          "msgs",
          rows.map((r) => r.msg_type),
          rows.map((r) => r.count),
          "#3fb950"
        );
      })
      .catch(() => {});
  }

  function loadCritical() {
    fetch("/api/analytics/critical_values")
      .then((res) => res.json())
      .then((alerts) => renderCritical(alerts))
      .catch(() => {});
  }

  function renderCritical(alerts) {
    const list = el("pipeline-critical");
    if (!alerts || !alerts.length) {
      list.innerHTML = `<li class="pipeline-critical-empty muted">No critical values.</li>`;
      return;
    }
    list.innerHTML = alerts
      .map((a) => {
        const dir = a.direction === "high" ? "high" : "low";
        const arrow = dir === "high" ? "&#9650;" : "&#9660;";
        return `
          <li class="pipeline-critical-item">
            <span class="pipeline-critical-badge pipeline-critical-${dir}">${arrow} ${escapeHtml(a.value)}${escapeHtml(a.unit || "")}</span>
            <span class="pipeline-critical-test">${escapeHtml(a.display_name)}</span>
            <span class="pipeline-critical-patient muted">${escapeHtml(a.full_name)}</span>
          </li>`;
      })
      .join("");
  }

  // ───────────── lifecycle ─────────────

  function refresh() {
    loadFeed();
    // Charts must size against a visible panel; render after layout settles.
    requestAnimationFrame(loadAnalytics);
  }

  function onPipelineTabOpened() {
    if (!patientsLoaded) {
      loadPatients();
    }
    refresh();
  }

  function init() {
    renderStages();

    el("pipeline-patient").addEventListener("change", updatePreview);
    el("pipeline-msgtype").addEventListener("change", updatePreview);
    el("pipeline-send").addEventListener("click", send);
    el("pipeline-reset").addEventListener("click", reset);

    const navBtn = document.querySelector('.nav-item[data-panel="pipeline"]');
    if (navBtn) {
      navBtn.addEventListener("click", () => requestAnimationFrame(onPipelineTabOpened));
    }

    // Load the patient list up front so the preview is ready on first open.
    loadPatients();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
