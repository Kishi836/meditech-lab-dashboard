/* Meditech Lab 2.0 — Extractor panel behaviour
   - POSTs the note textarea to /api/extract.
   - Renders the note with <mark> highlights positioned by the entity
     offsets returned by the API (cursor-walk, guarding against any span
     that starts before the cursor so adjacent/overlapping spans never
     corrupt the text).
   - Renders an entity table (Label, Value, Start, End) with a colour
     swatch matching each highlight. */

(function () {
  "use strict";

  // Group labels into a few tasteful colour buckets for the dark theme:
  // vitals, labs, and codes. Anything unknown falls back to the default.
  const LABEL_GROUP = {
    "BP": "vital",
    "HR": "vital",
    "Weight": "vital",
    "SpO2": "vital",
    "Blood Glucose": "lab",
    "HbA1c": "lab",
    "Creatinine": "lab",
    "eGFR": "lab",
    "Platelets": "lab",
    "Microalbumin": "lab",
    "ICD-10": "code",
  };

  function el(id) {
    return document.getElementById(id);
  }

  function slugify(label) {
    return String(label).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  function groupOf(label) {
    return LABEL_GROUP[label] || "default";
  }

  function setStatus(message) {
    el("extractor-status").textContent = message || "";
  }

  function runExtract() {
    const text = el("extractor-text").value;
    setStatus("Extracting…");

    fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.error) {
          setStatus(data.error);
          return;
        }
        setStatus(`${data.entities.length} entities found.`);
        renderHighlight(text, data.entities);
        renderTable(data.entities);
      })
      .catch(() => setStatus("Extraction failed — is the server running?"));
  }

  // Walk the text and the (already sorted) entity offsets, emitting escaped
  // plain text between entities and an escaped <mark> for each span.
  function renderHighlight(text, entities) {
    const target = el("extractor-highlight");
    let html = "";
    let cursor = 0;

    entities.forEach((ent) => {
      const start = ent.start;
      const end = ent.end;
      // Guard: skip any span that would step backwards (overlap/dup).
      if (start < cursor) return;

      html += escapeHtml(text.slice(cursor, start));
      const slug = slugify(ent.label);
      const group = groupOf(ent.label);
      html += `<mark class="ent ent-${group} ent-${slug}" title="${escapeHtml(ent.label)}">`;
      html += escapeHtml(text.slice(start, end));
      html += "</mark>";
      cursor = end;
    });

    html += escapeHtml(text.slice(cursor));
    target.innerHTML = html || `<span class="muted">Nothing to show.</span>`;
  }

  function renderTable(entities) {
    const table = el("extractor-table");
    const body = el("extractor-table-body");
    const empty = el("extractor-empty");
    body.innerHTML = "";

    if (!Array.isArray(entities) || entities.length === 0) {
      table.hidden = true;
      empty.hidden = false;
      empty.textContent = "No entities found.";
      return;
    }

    empty.hidden = true;
    table.hidden = false;

    entities.forEach((ent) => {
      const group = groupOf(ent.label);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="extractor-cell-label">
          <span class="extractor-swatch ent-${group}"></span>${escapeHtml(ent.label)}
        </td>
        <td class="extractor-cell-value">${escapeHtml(ent.value)}</td>
        <td class="extractor-cell-num">${escapeHtml(ent.start)}</td>
        <td class="extractor-cell-num">${escapeHtml(ent.end)}</td>
      `;
      body.appendChild(tr);
    });
  }

  // Escapes &<> (via textContent) plus quotes, so the result is safe both
  // as element text and inside a double-quoted attribute (e.g. title="…").
  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value == null ? "" : value);
    return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  document.addEventListener("DOMContentLoaded", () => {
    el("extractor-run").addEventListener("click", runExtract);
  });
})();
