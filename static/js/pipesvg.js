/* Meditech Lab 2.5 — PipeSVG: the animated SVG pipeline diagram.

   A reusable renderer for the six-stage hybrid pipeline. Draws the stages
   as SVG nodes (stroke icons, real/sim badge) joined by wires, plus an HTML
   caption strip underneath. `play(stages)` animates a little HL7 document
   packet travelling the wire node to node, lighting each stage green / grey
   / red as the backend reported it; a failed stage stops the packet there.

   Usage:
     const pipe = PipeSVG.mount(containerEl, { compact: true|false });
     pipe.play(stagesArray).then(() => ...);   // stages = [{stage,status,ms,detail}]
     pipe.reset();

   Used by the Pipeline panel (full size) and the Intake forms (compact).
   Honors prefers-reduced-motion by painting results instantly. */

(function () {
  "use strict";

  const STAGES = [
    { key: "build",         label: "Build",         sub: "HL7 v2.5", kind: "real", icon: "doc" },
    { key: "nifi_route",    label: "NiFi",          sub: "route",    kind: "sim",  icon: "route" },
    { key: "postgres",      label: "Postgres",      sub: "insert",   kind: "real", icon: "db" },
    { key: "elasticsearch", label: "Elasticsearch", sub: "index",    kind: "real", icon: "search" },
    { key: "kibana",        label: "Kibana",        sub: "charts",   kind: "sim",  icon: "chart" },
    { key: "minio",         label: "MinIO",         sub: "archive",  kind: "sim",  icon: "box" },
  ];

  // Geometry (viewBox units).
  const NODE_W = 150, NODE_H = 96, GAP = 44, MARGIN = 14, TOP = 10;
  const VIEW_W = MARGIN * 2 + STAGES.length * NODE_W + (STAGES.length - 1) * GAP;
  const VIEW_H = TOP + NODE_H + 14;
  const WIRE_Y = TOP + NODE_H / 2;

  const HOP_MS = 380;    // packet travel per hop
  const DWELL_MS = 170;  // pause while a node lights up

  // 24x24 stroke icons.
  const ICONS = {
    doc:    '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/><path d="M10 12h7M10 15h7M10 18h4"/>',
    route:  '<circle cx="4.5" cy="12" r="2"/><path d="M6.5 12H11"/><path d="M11 12c3.5 0 3.5-5.5 7-5.5M11 12c3.5 0 3.5 5.5 7 5.5M11 12h7"/><circle cx="20" cy="6.5" r="1.5"/><circle cx="20" cy="12" r="1.5"/><circle cx="20" cy="17.5" r="1.5"/>',
    db:     '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5V18.5c0 1.66 3.58 3 8 3s8-1.34 8-3V5.5"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.3 15.3L21 21"/>',
    chart:  '<path d="M4 21h17"/><rect x="6" y="12.5" width="3.2" height="8.5" rx="0.6"/><rect x="11.2" y="7.5" width="3.2" height="13.5" rx="0.6"/><rect x="16.4" y="10.5" width="3.2" height="10.5" rx="0.6"/>',
    box:    '<path d="M3.5 8L12 3.5 20.5 8v9L12 21.5 3.5 17z"/><path d="M3.5 8L12 12.5 20.5 8M12 12.5v9"/>',
  };

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value == null ? "" : value);
    return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function reducedMotion() {
    return window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function nodeX(i) {
    return MARGIN + i * (NODE_W + GAP);
  }

  function nodeCX(i) {
    return nodeX(i) + NODE_W / 2;
  }

  // ───────────── markup builders ─────────────

  function nodeMarkup(s, i) {
    const x = nodeX(i);
    const cx = nodeCX(i);
    return `
      <g class="pipesvg-node" id="pipesvg-node-${s.key}" data-kind="${s.kind}">
        <title id="pipesvg-title-${s.key}">${escapeHtml(s.label)}</title>
        <rect class="pipesvg-box" x="${x}" y="${TOP}" width="${NODE_W}" height="${NODE_H}" rx="12"/>
        <g class="pipesvg-badge pipesvg-badge-${s.kind}">
          <rect x="${x + NODE_W - 42}" y="${TOP + 8}" width="34" height="14" rx="7"/>
          <text x="${x + NODE_W - 25}" y="${TOP + 18.5}">${s.kind}</text>
        </g>
        <g class="pipesvg-icon" transform="translate(${cx - 14}, ${TOP + 12}) scale(1.166)">${ICONS[s.icon]}</g>
        <text class="pipesvg-name" x="${cx}" y="${TOP + 62}">${escapeHtml(s.label)}</text>
        <text class="pipesvg-sub" x="${cx}" y="${TOP + 78}">${escapeHtml(s.sub)}</text>
      </g>`;
  }

  function wireMarkup(i) {
    const x1 = nodeX(i) + NODE_W;
    const x2 = nodeX(i + 1);
    return `
      <line class="pipesvg-wire" id="pipesvg-wire-${i}"
            x1="${x1}" y1="${WIRE_Y}" x2="${x2}" y2="${WIRE_Y}"/>
      <line class="pipesvg-wire-pulse" id="pipesvg-wire-pulse-${i}"
            x1="${x1}" y1="${WIRE_Y}" x2="${x2}" y2="${WIRE_Y}"/>`;
  }

  // The travelling HL7 document packet (little page with a folded corner).
  const PACKET = `
    <g class="pipesvg-packet" id="pipesvg-packet" transform="translate(-40,-40)">
      <path d="M-7 -10 h9 l5 5 v15 h-14 z"/>
      <path d="M2 -10 v5 h5"/>
      <path d="M-4 0 h8 M-4 4 h8"/>
    </g>`;

  function svgMarkup() {
    const nodes = STAGES.map(nodeMarkup).join("");
    const wires = STAGES.slice(0, -1).map((_, i) => wireMarkup(i)).join("");
    return `
      <svg class="pipesvg-svg" viewBox="0 0 ${VIEW_W} ${VIEW_H}"
           role="img" aria-label="HL7 pipeline diagram">
        ${wires}${nodes}${PACKET}
      </svg>`;
  }

  function captionsMarkup() {
    const cells = STAGES.map((s) => `
      <div class="pipesvg-caption" id="pipesvg-caption-${s.key}"></div>`).join("");
    return `<div class="pipesvg-captions">${cells}</div>`;
  }

  // ───────────── instance ─────────────

  function mount(container, opts) {
    const compact = !!(opts && opts.compact);
    container.classList.add("pipesvg");
    container.classList.toggle("pipesvg-compact", compact);
    container.innerHTML = svgMarkup() + captionsMarkup();

    const packet = container.querySelector("#pipesvg-packet");

    function node(key) {
      return container.querySelector(`#pipesvg-node-${key}`);
    }

    function setPacket(x, instant) {
      packet.classList.toggle("pipesvg-packet-instant", !!instant);
      packet.setAttribute("transform", `translate(${x}, ${WIRE_Y})`);
      // SVG `transform` attribute changes don't animate — drive it via CSS.
      packet.style.transform = `translate(${x}px, ${WIRE_Y}px)`;
    }

    function light(result) {
      const g = node(result.stage);
      if (g) g.classList.add(`pipesvg-${result.status}`);
      const cap = container.querySelector(`#pipesvg-caption-${result.stage}`);
      if (cap) {
        cap.innerHTML =
          `<span class="pipesvg-caption-${escapeHtml(result.status)}">` +
          `${escapeHtml(result.detail)} · ${escapeHtml(result.ms)}ms</span>`;
      }
      const title = container.querySelector(`#pipesvg-title-${result.stage}`);
      if (title) title.textContent = `${result.detail} · ${result.ms}ms`;
    }

    function activateWire(i, status) {
      const pulse = container.querySelector(`#pipesvg-wire-pulse-${i}`);
      if (pulse) pulse.classList.add("pipesvg-wire-active");
    }

    function sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    function reset() {
      STAGES.forEach((s) => {
        const g = node(s.key);
        if (g) g.classList.remove("pipesvg-ok", "pipesvg-skipped", "pipesvg-error");
        const cap = container.querySelector(`#pipesvg-caption-${s.key}`);
        if (cap) cap.innerHTML = "";
        const title = container.querySelector(`#pipesvg-title-${s.key}`);
        if (title) title.textContent = s.label;
      });
      STAGES.slice(0, -1).forEach((_, i) => {
        const pulse = container.querySelector(`#pipesvg-wire-pulse-${i}`);
        if (pulse) pulse.classList.remove("pipesvg-wire-active");
      });
      packet.classList.remove("pipesvg-packet-visible", "pipesvg-packet-dead");
      setPacket(nodeCX(0), true);
    }

    async function play(stageResults) {
      reset();
      if (!stageResults || !stageResults.length) return;

      if (reducedMotion()) {
        stageResults.forEach(light);
        return;
      }

      packet.classList.add("pipesvg-packet-visible");
      setPacket(nodeCX(0), true);
      await sleep(30); // let the instant position commit before transitioning

      for (let i = 0; i < stageResults.length; i++) {
        const result = stageResults[i];
        if (i > 0) {
          activateWire(i - 1, result.status);
          setPacket(nodeCX(i), false);
          await sleep(HOP_MS);
        }
        light(result);
        if (result.status === "error") {
          packet.classList.add("pipesvg-packet-dead");
          return;
        }
        await sleep(DWELL_MS);
      }
      packet.classList.remove("pipesvg-packet-visible");
    }

    reset();
    return { play, reset };
  }

  window.PipeSVG = { mount };
})();
