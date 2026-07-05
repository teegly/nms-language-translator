"use strict";

// Fixed language priority for detection ties (V11).
const PRIORITY = ["Gek", "Korvax", "Vy'keen", "Autophage", "Atlas"];

// Sentence punctuation stripped from token edges during normalization (V9).
// Intra-word ' and - are preserved.
const EDGE_PUNCT = ".,!?;:";

let LANGS = {};        // faction -> { dict, maxSpan }
let ready = false;

const el = {
  input: document.getElementById("input"),
  output: document.getElementById("output"),
  detected: document.getElementById("detected"),
  langName: document.getElementById("lang-name"),
  langLabel: document.getElementById("lang-label"),
  langConf: document.getElementById("lang-conf"),
  langSelect: document.getElementById("lang-select"),
  status: document.getElementById("status"),
};

// Strip leading/trailing sentence punctuation from a raw token (V9).
// Returns { lead, core, trail } so matched output can re-attach punctuation.
function splitToken(tok) {
  let start = 0, end = tok.length;
  while (start < end && EDGE_PUNCT.includes(tok[start])) start++;
  while (end > start && EDGE_PUNCT.includes(tok[end - 1])) end--;
  return { lead: tok.slice(0, start), core: tok.slice(start, end), trail: tok.slice(end) };
}

// Normalize a core token for case- and punctuation-insensitive lookup (V4).
function normCore(core) {
  return core.toLowerCase();
}

// Greedy longest-key match over normalized cores starting at index i (V10).
// Returns { span, en } if a key matches, else null.
function matchAt(dict, maxSpan, cores, i) {
  const limit = Math.min(maxSpan, cores.length - i);
  for (let span = limit; span >= 1; span--) {
    const key = cores.slice(i, i + span).join(" ");
    if (Object.prototype.hasOwnProperty.call(dict, key)) {
      return { span, en: dict[key].en };
    }
  }
  return null;
}

// Count how many tokens a language matches (for detection, V2).
function matchedTokenCount(lang, cores) {
  const { dict, maxSpan } = LANGS[lang];
  let i = 0, matched = 0;
  while (i < cores.length) {
    const m = matchAt(dict, maxSpan, cores, i);
    if (m) { matched += m.span; i += m.span; }
    else i++;
  }
  return matched;
}

// Pick the language with the most matched tokens; ties broken by PRIORITY (V2, V11).
function detect(cores) {
  let best = null, bestCount = 0;
  for (const lang of PRIORITY) {
    const c = matchedTokenCount(lang, cores);
    if (c > bestCount) { best = lang; bestCount = c; }
  }
  return { lang: best, count: bestCount };
}

// Translate the raw tokens using the detected language.
// Matched keys -> English (punctuation re-attached); unmatched -> verbatim (V3).
function translate(lang, rawTokens, parts) {
  const { dict, maxSpan } = LANGS[lang];
  const cores = parts.map(p => normCore(p.core));
  const outHtml = [];
  let i = 0;
  while (i < rawTokens.length) {
    const m = matchAt(dict, maxSpan, cores, i);
    if (m) {
      const lead = parts[i].lead;
      const trail = parts[i + m.span - 1].trail;
      outHtml.push(escapeHtml(lead + m.en + trail));
      i += m.span;
    } else {
      outHtml.push('<span class="passthrough">' + escapeHtml(rawTokens[i]) + "</span>");
      i++;
    }
  }
  return outHtml.join(" ");
}

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function render() {
  if (!ready) return;
  const text = el.input.value.trim();
  if (!text) {
    el.output.textContent = "";
    el.detected.hidden = true;
    return;
  }
  const rawTokens = text.split(/\s+/);
  const parts = rawTokens.map(splitToken);
  const cores = parts.map(p => normCore(p.core));

  // Manual override forces a language; "auto" runs detection (V19).
  const override = el.langSelect.value;
  let lang, count, forced = false;
  if (override !== "auto") {
    lang = override;
    count = matchedTokenCount(lang, cores);
    forced = true;
  } else {
    ({ lang, count } = detect(cores));
  }

  if (!lang) {
    el.detected.hidden = true;
    el.output.innerHTML = '<span class="passthrough">' + escapeHtml(text) + "</span>";
    return;
  }
  el.detected.hidden = false;
  el.langLabel.textContent = forced ? "Language:" : "Detected language:";
  el.langName.textContent = lang;
  el.langConf.textContent = `(${count}/${rawTokens.length} words matched)`;
  el.output.innerHTML = translate(lang, rawTokens, parts);
}

function load() {
  fetch("data/languages.json")
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(data => {
      for (const [lang, dict] of Object.entries(data)) {
        let maxSpan = 1;
        for (const key of Object.keys(dict)) {
          const span = key.split(" ").length;
          if (span > maxSpan) maxSpan = span;
        }
        LANGS[lang] = { dict, maxSpan };
      }
      ready = true;
      const total = Object.values(data).reduce((n, d) => n + Object.keys(d).length, 0);
      el.status.textContent = `${total.toLocaleString()} words across ${Object.keys(data).length} languages.`;
      render();
    })
    .catch(err => {
      el.status.textContent = "Failed to load data/languages.json (" + err.message +
        "). Serve the folder over http (e.g. `python -m http.server`) rather than opening the file directly.";
      el.status.className = "error";
    });
}

el.input.addEventListener("input", render);
el.langSelect.addEventListener("change", render);
load();
