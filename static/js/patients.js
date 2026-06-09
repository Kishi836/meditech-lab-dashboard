/* Meditech Lab 2.0 — Patients panel behaviour
   - Left: searchable patient list (GET /api/patients?q=). Clicking a row
     loads that patient's detail.
   - Right: a tabbed record — Overview (demographics), Encounters (table),
     Labs (Chart.js line charts of observation trends + a table), Meds.
   - Trend charts colour each point by its high/low/normal flag. If Chart.js
     failed to load (offline), the Labs tab degrades to the table only.
   - If the list fetch fails (Postgres down), a friendly banner is shown. */

(function () {
  "use strict";

  const FLAG_COLOR = {
    high: "#c0392b",   // --red
    low: "#2563eb",    // --blue
    normal: "#0f8a5f", // --green
  };

  let selectedId = null;
  let activeTab = "overview";
  const charts = []; // live Chart instances, destroyed before each re-render

  function el(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value == null ? "" : value);
    return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function fmt(value) {
    return value == null || value === "" ? "—" : String(value);
  }

  // ───────────── patient list ─────────────

  function showBanner(message) {
    const banner = el("patients-banner");
    banner.textContent = message;
    banner.hidden = false;
  }

  function hideBanner() {
    el("patients-banner").hidden = true;
  }

  function loadList(q) {
    const url = q
      ? `/api/patients?q=${encodeURIComponent(q)}`
      : "/api/patients";

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((patients) => {
        hideBanner();
        renderList(patients);
        // Auto-select the first patient on initial (unfiltered) load.
        if (selectedId === null && Array.isArray(patients) && patients.length) {
          loadPatient(patients[0].patient_id);
        }
      })
      .catch(() => {
        renderList([]);
        showBanner("Couldn't reach the database — is Postgres running?");
      });
  }

  function renderList(patients) {
    const list = el("patients-list");
    list.innerHTML = "";

    if (!Array.isArray(patients) || patients.length === 0) {
      const li = document.createElement("li");
      li.className = "patients-list-message muted";
      li.textContent = "No matching patients.";
      list.appendChild(li);
      return;
    }

    patients.forEach((p) => {
      const li = document.createElement("li");
      li.className = "patients-list-item";
      li.setAttribute("data-patient-id", p.patient_id);
      if (p.patient_id === selectedId) li.classList.add("active");
      li.innerHTML = `
        <div class="patients-list-top">
          <span class="patients-list-name">${escapeHtml(p.full_name)}</span>
          <span class="patients-list-meta">${escapeHtml(p.gender)} · ${escapeHtml(p.age)}y</span>
        </div>
        <div class="patients-list-mrn">${escapeHtml(p.mrn)}</div>
        <div class="patients-list-summary muted">${escapeHtml(p.summary)}</div>
      `;
      li.addEventListener("click", () => loadPatient(p.patient_id));
      list.appendChild(li);
    });
  }

  // ───────────── patient detail ─────────────

  function loadPatient(id) {
    selectedId = id;
    markActiveRow();

    fetch(`/api/patients/${encodeURIComponent(id)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        // Trends come from a dedicated endpoint so the chart series are
        // already grouped per test.
        return fetch(`/api/patients/${encodeURIComponent(id)}/trends`)
          .then((res) => (res.ok ? res.json() : {}))
          .then((trends) => renderRecord(data, trends));
      })
      .catch(() => {
        el("patients-record").hidden = true;
        const empty = el("patients-detail-empty");
        empty.hidden = false;
        empty.textContent = "Couldn't load that patient.";
      });
  }

  function markActiveRow() {
    document.querySelectorAll(".patients-list-item").forEach((row) => {
      row.classList.toggle(
        "active",
        row.getAttribute("data-patient-id") === selectedId
      );
    });
  }

  function renderRecord(data, trends) {
    el("patients-detail-empty").hidden = true;
    el("patients-record").hidden = false;

    const demo = data.demographics || {};
    el("patients-record-name").textContent = demo.full_name || "";
    el("patients-record-id").textContent =
      `${demo.patient_id || ""} · ${demo.mrn || ""}`;

    renderOverview(demo);
    renderEncounters(data.encounters || []);
    renderLabs(data.observations || [], trends || {});
    renderMeds(data.medications || [], data.conditions || []);

    setTab(activeTab);
  }

  function renderOverview(demo) {
    const panel = el("patients-tab-overview");
    const rows = [
      ["Full name", demo.full_name],
      ["Patient ID", demo.patient_id],
      ["MRN", demo.mrn],
      ["Age", demo.age != null ? `${demo.age} years` : null],
      ["Date of birth", demo.dob],
      ["Gender", demo.gender],
      ["Blood type", demo.blood_type],
      ["Phone", demo.phone],
      ["City", demo.city],
    ];
    const dl = rows
      .map(
        ([k, v]) => `
          <dt>${escapeHtml(k)}</dt>
          <dd>${escapeHtml(fmt(v))}</dd>`
      )
      .join("");
    panel.innerHTML = `<dl class="patients-demo">${dl}</dl>`;
  }

  function renderEncounters(encounters) {
    const panel = el("patients-tab-encounters");
    if (!encounters.length) {
      panel.innerHTML = `<p class="muted">No encounters on record.</p>`;
      return;
    }
    const body = encounters
      .map(
        (e) => `
          <tr>
            <td>${escapeHtml(fmt(e.enc_date))}</td>
            <td>${escapeHtml(fmt(e.enc_type))}</td>
            <td>${escapeHtml(fmt(e.department))}</td>
            <td>${escapeHtml(fmt(e.attending_dr))}</td>
            <td>${escapeHtml(fmt(e.discharge_dt))}</td>
          </tr>`
      )
      .join("");
    panel.innerHTML = `
      <table class="patients-table">
        <thead><tr>
          <th>Date</th><th>Type</th><th>Department</th>
          <th>Attending</th><th>Discharge</th>
        </tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  function renderMeds(medications, conditions) {
    const panel = el("patients-tab-meds");
    let html = "";

    if (conditions.length) {
      const condBody = conditions
        .map(
          (c) => `
            <tr>
              <td class="patients-mono">${escapeHtml(fmt(c.icd10_code))}</td>
              <td>${escapeHtml(fmt(c.description))}</td>
              <td>${escapeHtml(fmt(c.onset_date))}</td>
              <td><span class="patients-status patients-status-${escapeHtml(c.status)}">${escapeHtml(fmt(c.status))}</span></td>
            </tr>`
        )
        .join("");
      html += `
        <h3 class="patients-subhead">Conditions</h3>
        <table class="patients-table">
          <thead><tr><th>ICD-10</th><th>Description</th><th>Onset</th><th>Status</th></tr></thead>
          <tbody>${condBody}</tbody>
        </table>`;
    }

    html += `<h3 class="patients-subhead">Medications</h3>`;
    if (!medications.length) {
      html += `<p class="muted">No medications on record.</p>`;
    } else {
      const medBody = medications
        .map(
          (m) => `
            <tr>
              <td>${escapeHtml(fmt(m.drug_name))}</td>
              <td>${escapeHtml(fmt(m.dose))}</td>
              <td>${escapeHtml(fmt(m.frequency))}</td>
              <td>${escapeHtml(fmt(m.start_date))}</td>
              <td>${escapeHtml(fmt(m.end_date))}</td>
            </tr>`
        )
        .join("");
      html += `
        <table class="patients-table">
          <thead><tr><th>Drug</th><th>Dose</th><th>Frequency</th><th>Start</th><th>End</th></tr></thead>
          <tbody>${medBody}</tbody>
        </table>`;
    }
    panel.innerHTML = html;
  }

  // ───────────── labs: charts + table ─────────────

  function renderLabs(observations, trends) {
    const panel = el("patients-tab-labs");
    destroyCharts();

    const testNames = Object.keys(trends);
    if (!testNames.length && !observations.length) {
      panel.innerHTML = `<p class="muted">No observations on record.</p>`;
      return;
    }

    const chartsAvailable = typeof Chart !== "undefined";
    let html = "";

    if (testNames.length) {
      if (!chartsAvailable) {
        html += `<p class="muted patients-chart-note">Charts unavailable (Chart.js didn't load) — showing values below.</p>`;
      }
      html += `<div class="patients-charts" id="patients-charts"></div>`;
    }

    // A flat table of every observation as a reliable fallback / detail view.
    const obsBody = observations
      .map(
        (o) => `
          <tr>
            <td>${escapeHtml(fmt(o.obs_date))}</td>
            <td>${escapeHtml(fmt(o.display_name))}</td>
            <td class="patients-mono">${escapeHtml(o.value == null ? "—" : o.value)}</td>
            <td>${escapeHtml(fmt(o.unit))}</td>
            <td><span class="patients-flag patients-flag-${escapeHtml(o.flag)}">${escapeHtml(fmt(o.flag))}</span></td>
          </tr>`
      )
      .join("");
    html += `
      <h3 class="patients-subhead">All observations</h3>
      <table class="patients-table">
        <thead><tr><th>Date</th><th>Test</th><th>Value</th><th>Unit</th><th>Flag</th></tr></thead>
        <tbody>${obsBody}</tbody>
      </table>`;

    panel.innerHTML = html;

    if (testNames.length && chartsAvailable) {
      buildCharts(testNames, trends);
    }
  }

  function buildCharts(testNames, trends) {
    const host = el("patients-charts");
    if (!host) return;

    testNames.forEach((name, idx) => {
      const series = trends[name] || [];
      const unit = (series[0] && series[0].unit) || "";

      const card = document.createElement("div");
      card.className = "patients-chart-card";
      card.innerHTML = `
        <div class="patients-chart-title">${escapeHtml(name)}${unit ? ` <span class="muted">(${escapeHtml(unit)})</span>` : ""}</div>
        <div class="patients-chart-canvas-wrap"><canvas id="patients-chart-${idx}"></canvas></div>`;
      host.appendChild(card);

      const canvas = card.querySelector("canvas");
      const labels = series.map((p) => p.date);
      const values = series.map((p) => p.value);
      const pointColors = series.map((p) => FLAG_COLOR[p.flag] || FLAG_COLOR.normal);

      const chart = new Chart(canvas.getContext("2d"), {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            {
              label: name,
              data: values,
              borderColor: "#8b949e",
              backgroundColor: "rgba(139,148,158,0.12)",
              pointBackgroundColor: pointColors,
              pointBorderColor: pointColors,
              pointRadius: 5,
              pointHoverRadius: 7,
              tension: 0.25,
              fill: false,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const p = series[ctx.dataIndex] || {};
                  return `${ctx.parsed.y} ${unit} (${p.flag})`;
                },
              },
            },
          },
          scales: {
            x: { ticks: { color: "#6b7a8d" }, grid: { color: "#e5e9f0" } },
            y: { ticks: { color: "#6b7a8d" }, grid: { color: "#e5e9f0" } },
          },
        },
      });
      charts.push(chart);
    });
  }

  function destroyCharts() {
    while (charts.length) {
      const c = charts.pop();
      try {
        c.destroy();
      } catch (e) {
        /* ignore */
      }
    }
  }

  // ───────────── tabs ─────────────

  function setTab(tab) {
    activeTab = tab;
    document.querySelectorAll(".patients-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-tab") === tab);
    });
    document.querySelectorAll(".patients-tabpanel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === `patients-tab-${tab}`);
    });
  }

  function initTabs() {
    document.querySelectorAll(".patients-tab").forEach((btn) => {
      btn.addEventListener("click", () => setTab(btn.getAttribute("data-tab")));
    });
  }

  function initSearch() {
    el("patients-search-form").addEventListener("submit", (evt) => {
      evt.preventDefault();
      loadList(el("patients-search-input").value.trim());
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initSearch();
    loadList("");
  });
})();
