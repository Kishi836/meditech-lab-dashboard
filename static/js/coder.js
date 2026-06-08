/* Meditech Lab 2.0 — Coder panel behaviour
   - Toggle between SNOMED CT and ICD-10 search.
   - Render result lists; clicking a SNOMED result loads its concept card
     (FSN, attributes, ancestor → concept → children hierarchy tree).
   - "Cross-map to ICD-10" calls /api/crossmap/<id> for the selected concept.
   ICD-10 results are informational (no detail card — they're terminal codes,
   not a hierarchy to browse), each annotated with its own SNOMED cross-map
   when one is known. */

(function () {
  "use strict";

  let mode = "snomed"; // "snomed" | "icd10"
  let selectedSnomedId = null;

  function el(id) {
    return document.getElementById(id);
  }

  function setMode(newMode) {
    mode = newMode;
    document.querySelectorAll(".coder-toggle-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-mode") === mode);
    });

    const input = el("coder-search-input");
    const hint = el("coder-hint");
    if (mode === "snomed") {
      input.placeholder = "Search SNOMED concepts (e.g. diabetes, heart failure, 44054006)…";
      hint.textContent = "Searching SNOMED CT concepts by name or numeric id.";
    } else {
      input.placeholder = "Search ICD-10 codes or descriptions (e.g. diabetes, E11, pneumonia)…";
      hint.textContent = "Searching ICD-10 codes by code or description.";
    }

    el("coder-results").innerHTML = "";
  }

  function initToggle() {
    document.querySelectorAll(".coder-toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => setMode(btn.getAttribute("data-mode")));
    });
  }

  function initSearchForm() {
    el("coder-search-form").addEventListener("submit", (evt) => {
      evt.preventDefault();
      const q = el("coder-search-input").value.trim();
      if (!q) return;

      if (mode === "snomed") {
        runSnomedSearch(q);
      } else {
        runIcd10Search(q);
      }
    });
  }

  function showResultsMessage(message) {
    const list = el("coder-results");
    list.innerHTML = "";
    const li = document.createElement("li");
    li.className = "coder-result-message muted";
    li.textContent = message;
    list.appendChild(li);
  }

  // ───────────── SNOMED search → results → detail card ─────────────

  function runSnomedSearch(q) {
    showResultsMessage("Searching…");

    fetch(`/api/snomed/search?q=${encodeURIComponent(q)}`)
      .then((res) => res.json())
      .then((data) => renderSnomedResults(data))
      .catch(() => showResultsMessage("Search failed — is the server running?"));
  }

  function renderSnomedResults(concepts) {
    const list = el("coder-results");
    list.innerHTML = "";

    if (!Array.isArray(concepts) || concepts.length === 0) {
      showResultsMessage("No matching SNOMED concepts.");
      return;
    }

    concepts.forEach((concept) => {
      const li = document.createElement("li");
      li.className = "coder-result";
      li.innerHTML = `
        <span class="coder-result-id">${concept.id}</span>
        <span class="coder-result-fsn">${escapeHtml(concept.fsn)}</span>
      `;
      li.addEventListener("click", () => loadSnomedConcept(concept.id));
      list.appendChild(li);
    });
  }

  function loadSnomedConcept(id) {
    selectedSnomedId = id;

    fetch(`/api/snomed/${encodeURIComponent(id)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((concept) => renderConceptCard(concept))
      .catch(() => {
        el("coder-card").hidden = true;
        el("coder-detail-empty").hidden = false;
        el("coder-detail-empty").textContent = "Couldn't load that concept.";
      });
  }

  function renderConceptCard(concept) {
    el("coder-detail-empty").hidden = true;
    const card = el("coder-card");
    card.hidden = false;

    el("coder-card-id").textContent = concept.id;
    el("coder-card-fsn").textContent = concept.fsn;

    // Attributes
    const attrsSection = el("coder-attrs-section");
    const attrsList = el("coder-attrs");
    attrsList.innerHTML = "";
    const attrs = concept.attributes || {};
    const attrKeys = Object.keys(attrs);
    if (attrKeys.length > 0) {
      attrKeys.forEach((key) => {
        const dt = document.createElement("dt");
        dt.textContent = formatAttrKey(key);
        const dd = document.createElement("dd");
        dd.textContent = attrs[key];
        attrsList.appendChild(dt);
        attrsList.appendChild(dd);
      });
      attrsSection.hidden = false;
    } else {
      attrsSection.hidden = true;
    }

    // Hierarchy tree: ancestors (root first) → concept → children
    renderHierarchyTree(concept);

    // Reset cross-map result for the newly selected concept
    el("coder-crossmap-result").textContent = "";
    el("coder-crossmap-result").className = "coder-crossmap-result";
  }

  function renderHierarchyTree(concept) {
    const section = el("coder-tree-section");
    const tree = el("coder-tree");
    tree.innerHTML = "";

    const ancestors = concept.ancestors || []; // immediate parent first
    const children = concept.children || [];

    if (ancestors.length === 0 && children.length === 0) {
      section.hidden = true;
      return;
    }
    section.hidden = false;

    // Ancestors come back [immediate parent, ..., root]; show root → … → parent
    const rootFirst = ancestors.slice().reverse();
    let depth = 0;

    rootFirst.forEach((ancestor) => {
      tree.appendChild(makeTreeNode(ancestor.id, ancestor.fsn, depth, "ancestor"));
      depth += 1;
    });

    tree.appendChild(makeTreeNode(concept.id, concept.fsn, depth, "current"));
    depth += 1;

    children.forEach((child) => {
      tree.appendChild(makeTreeNode(child.id, child.fsn, depth, "child"));
    });
  }

  function makeTreeNode(id, fsn, depth, kind) {
    const row = document.createElement("div");
    row.className = `coder-tree-node coder-tree-${kind}`;
    row.style.paddingLeft = `${depth * 20}px`;
    row.innerHTML = `
      <span class="coder-tree-bullet">${kind === "current" ? "▸" : "·"}</span>
      <span class="coder-tree-id">${id}</span>
      <span class="coder-tree-fsn">${escapeHtml(fsn)}</span>
    `;
    if (kind !== "current") {
      row.classList.add("coder-tree-clickable");
      row.addEventListener("click", () => loadSnomedConcept(id));
    }
    return row;
  }

  function initCrossmapButton() {
    el("coder-crossmap-btn").addEventListener("click", () => {
      if (selectedSnomedId === null) return;

      const resultEl = el("coder-crossmap-result");
      resultEl.className = "coder-crossmap-result";
      resultEl.textContent = "Mapping…";

      fetch(`/api/crossmap/${encodeURIComponent(selectedSnomedId)}`)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then((data) => {
          if (data.icd10) {
            resultEl.textContent = `→ ICD-10: ${data.icd10}`;
            resultEl.className = "coder-crossmap-result ok";
          } else {
            resultEl.textContent = "No ICD-10 mapping known for this concept.";
            resultEl.className = "coder-crossmap-result none";
          }
        })
        .catch(() => {
          resultEl.textContent = "Cross-map lookup failed.";
          resultEl.className = "coder-crossmap-result error";
        });
    });
  }

  // ───────────── ICD-10 search ─────────────

  function runIcd10Search(q) {
    showResultsMessage("Searching…");

    fetch(`/api/icd10?q=${encodeURIComponent(q)}`)
      .then((res) => res.json())
      .then((data) => renderIcd10Results(data))
      .catch(() => showResultsMessage("Search failed — is the server running?"));
  }

  function renderIcd10Results(entries) {
    const list = el("coder-results");
    list.innerHTML = "";

    if (!Array.isArray(entries) || entries.length === 0) {
      showResultsMessage("No matching ICD-10 codes.");
      return;
    }

    entries.forEach((entry) => {
      const li = document.createElement("li");
      li.className = "coder-result coder-result-icd10";
      li.innerHTML = `
        <span class="coder-result-id">${escapeHtml(entry.code)}</span>
        <span class="coder-result-fsn">${escapeHtml(entry.desc)}</span>
        <span class="coder-result-meta muted">Chapter ${escapeHtml(entry.chapter)} · Block ${escapeHtml(entry.block)}</span>
      `;
      list.appendChild(li);
    });
  }

  // ───────────── helpers ─────────────

  function formatAttrKey(key) {
    return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value == null ? "" : value);
    return div.innerHTML;
  }

  document.addEventListener("DOMContentLoaded", () => {
    initToggle();
    initSearchForm();
    initCrossmapButton();
  });
})();
