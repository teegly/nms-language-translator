"use strict";

// UI controller for the CRT terminal. All translation logic lives in engine.js
// (window.NMSEngine); this file only wires the DOM.

const el = {
  input: document.getElementById("input"),
  output: document.getElementById("output"),
  chips: Array.from(document.querySelectorAll(".chip")),
  readoutWord: document.getElementById("readout-word"),
  readoutValue: document.getElementById("readout-value"),
  meter: document.getElementById("meter"),
  tokens: document.getElementById("tokens"),
  foot: document.getElementById("foot"),
  photo: document.getElementById("photo"),
  ocrStatus: document.getElementById("ocr-status"),
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
    const active = lang === "auto" ? !override : override === lang;
    if (active) chip.classList.add("active");
    else if (!override && detectedLang === lang) chip.classList.add("detected");
    chip.setAttribute("aria-pressed", active ? "true" : "false");
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
  el.output.innerHTML = '<span class="blink cursor" aria-hidden="true">▮</span>';
}

function render() {
  const result = ready ? window.NMSEngine.analyze(LANGS, el.input.value, override) : null;

  if (!result) {
    // empty input (or not yet loaded)
    updateChips(null);
    el.readoutWord.textContent = "STATUS";
    el.readoutValue.textContent = "AWAITING INPUT";
    setMeter(0);
    el.tokens.textContent = "";
    renderEmpty();
    return;
  }

  if (!result.lang) {
    // no match
    updateChips(null);
    el.readoutWord.textContent = "STATUS";
    el.readoutValue.textContent = "NO MATCH";
    setMeter(0);
    el.tokens.textContent = result.count + " / " + result.total;
    renderOutput(result.segments);
    return;
  }

  updateChips(result.lang);
  el.readoutWord.textContent = "DETECTED";
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

// ---- photo OCR (T16) ----
// Tesseract.js is lazy-loaded from the CDN the first time the user picks an
// image, so the ~2MB OCR engine costs nothing on a normal text translation.
// OCR text lands in the #input textarea (user can edit it) and the existing
// input handler translates it — no new translation path.
const TESSERACT_SRC = "https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js";
let tesseractLoader = null;

function loadTesseract() {
  if (!tesseractLoader) {
    tesseractLoader = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = TESSERACT_SRC;
      s.onload = () => resolve(window.Tesseract);
      s.onerror = () => reject(new Error("could not load OCR engine"));
      document.head.appendChild(s);
    });
  }
  return tesseractLoader;
}

function setOcrStatus(text, state) {
  el.ocrStatus.textContent = text;
  el.ocrStatus.className = "ocr-status" + (state ? " " + state : "");
}

function runOcr(file) {
  setOcrStatus("LOADING OCR…", "busy");
  loadTesseract()
    .then((Tesseract) => {
      setOcrStatus("SCANNING 0%", "busy");
      return Tesseract.recognize(file, "eng", {
        logger: (m) => {
          if (m.status === "recognizing text") {
            setOcrStatus("SCANNING " + Math.round(m.progress * 100) + "%", "busy");
          }
        },
      });
    })
    .then(({ data }) => {
      const text = (data.text || "").trim();
      if (!text) {
        setOcrStatus("NO TEXT FOUND — TRY A CLEARER IMAGE", "error");
        return;
      }
      el.input.value = text;
      el.input.dispatchEvent(new Event("input"));
      setOcrStatus("SCANNED ✓ EDIT ABOVE IF NEEDED", "");
    })
    .catch((err) => {
      setOcrStatus("⚠ OCR FAILED — " + err.message, "error");
    });
}

el.photo.addEventListener("change", () => {
  const file = el.photo.files && el.photo.files[0];
  if (file) runOcr(file);
  el.photo.value = ""; // let the user re-pick the same file
});

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
