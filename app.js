"use strict";

// UI controller for the CRT terminal. All translation logic lives in engine.js
// (window.NMSEngine); this file only wires the DOM.

const el = {
  input: document.getElementById("input"),
  output: document.getElementById("output"),
  chips: Array.from(document.querySelectorAll(".chip")),
  readoutLabel: document.getElementById("readout-label"),
  readoutValue: document.getElementById("readout-value"),
  meter: document.getElementById("meter"),
  tokens: document.getElementById("tokens"),
  foot: document.getElementById("foot"),
};

let LANGS = null;
let ready = false;
let override = null; // null = auto-detect; else a faction name

// Build the 10 confidence-meter cells once; render() toggles .on.
const cells = [];
for (let i = 0; i < 10; i++) {
  const c = document.createElement("div");
  c.className = "cell";
  el.meter.appendChild(c);
  cells.push(c);
}

function setMeter(filled) {
  for (let i = 0; i < cells.length; i++) {
    cells[i].classList.toggle("on", i < filled);
  }
}

// Chip states (V22): AUTO active when no override; forced faction active;
// in auto mode the detected faction shows "detected"; everything else idle.
function updateChips(detectedLang) {
  for (const chip of el.chips) {
    const lang = chip.dataset.lang;
    chip.classList.remove("active", "detected");
    if (lang === "auto") {
      if (!override) chip.classList.add("active");
    } else if (override === lang) {
      chip.classList.add("active");
    } else if (!override && detectedLang === lang) {
      chip.classList.add("detected");
    }
  }
}

function renderOutput(segments) {
  el.output.className = "output";
  el.output.textContent = "";
  for (const seg of segments) {
    const span = document.createElement("span");
    span.className = seg.matched ? "seg-matched" : "seg-pass";
    span.textContent = seg.text;
    el.output.appendChild(span);
  }
}

function renderEmpty() {
  el.output.className = "output empty";
  el.output.innerHTML = '<span class="blink cursor">▮</span>';
}

function render() {
  const result = ready ? window.NMSEngine.analyze(LANGS, el.input.value, override) : null;

  if (!result) {
    // empty input (or not yet loaded)
    updateChips(null);
    el.readoutLabel.textContent = "STATUS ▸";
    el.readoutValue.textContent = "AWAITING INPUT";
    setMeter(0);
    el.tokens.textContent = "";
    renderEmpty();
    return;
  }

  if (!result.lang) {
    // no match
    updateChips(null);
    el.readoutLabel.textContent = "STATUS ▸";
    el.readoutValue.textContent = "NO MATCH";
    setMeter(0);
    el.tokens.textContent = result.count + " / " + result.total;
    renderOutput(result.segments);
    return;
  }

  updateChips(result.lang);
  el.readoutLabel.textContent = "DETECTED ▸";
  el.readoutValue.textContent = result.lang.toUpperCase();
  setMeter(Math.round((result.count / result.total) * 10));
  el.tokens.textContent = result.count + " / " + result.total;
  renderOutput(result.segments);
}

// ---- events ----
el.input.addEventListener("input", render);

el.chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const lang = chip.dataset.lang;
    if (lang === "auto") override = null;
    else override = override === lang ? null : lang; // toggle
    render();
  });
});

// Photo upload is intentionally a static COMING SOON placeholder — no file
// input, no picker, until OCR (T16) is actually wired.

// ---- load ----
window.NMSEngine.loadLangs()
  .then(({ LANGS: langs, total, langCount }) => {
    LANGS = langs;
    ready = true;
    el.foot.textContent = total.toLocaleString() + " WORDS · " + langCount + " LANGUAGES INDEXED";
    render();
  })
  .catch((err) => {
    el.foot.className = "foot error";
    el.foot.textContent = "⚠ DICTIONARY OFFLINE — SERVE OVER HTTP (" + err.message + ")";
  });

render();
