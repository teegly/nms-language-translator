/* NMS Language Translator engine — the translation logic, framework-free.
   Exposes window.NMSEngine. Caches the dictionary load.
   (Same matching logic the app has always used; separated from the UI.) */
(function () {
  "use strict";

  const PRIORITY = ["Gek", "Korvax", "Vy'keen", "Autophage", "Atlas"];
  const EDGE_PUNCT = ".,!?;:";

  let _promise = null;

  function loadLangs() {
    if (!_promise) {
      _promise = fetch("data/languages.json")
        .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then((data) => {
          const LANGS = {};
          for (const [lang, dict] of Object.entries(data)) {
            let maxSpan = 1;
            for (const key of Object.keys(dict)) {
              const span = key.split(" ").length;
              if (span > maxSpan) maxSpan = span;
            }
            LANGS[lang] = { dict, maxSpan };
          }
          const total = Object.values(data).reduce((n, d) => n + Object.keys(d).length, 0);
          return { LANGS, total, langCount: Object.keys(data).length };
        });
    }
    return _promise;
  }

  function splitToken(tok) {
    let start = 0, end = tok.length;
    while (start < end && EDGE_PUNCT.includes(tok[start])) start++;
    while (end > start && EDGE_PUNCT.includes(tok[end - 1])) end--;
    return { lead: tok.slice(0, start), core: tok.slice(start, end), trail: tok.slice(end) };
  }

  const normCore = (core) => core.toLowerCase();

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

  function matchedTokenCount(LANGS, lang, cores) {
    const { dict, maxSpan } = LANGS[lang];
    let i = 0, matched = 0;
    while (i < cores.length) {
      const m = matchAt(dict, maxSpan, cores, i);
      if (m) { matched += m.span; i += m.span; }
      else i++;
    }
    return matched;
  }

  function detect(LANGS, cores) {
    let best = null, bestCount = 0;
    for (const lang of PRIORITY) {
      const c = matchedTokenCount(LANGS, lang, cores);
      if (c > bestCount) { best = lang; bestCount = c; }
    }
    return { lang: best, count: bestCount };
  }

  function translateTokens(LANGS, lang, rawTokens, parts) {
    const { dict, maxSpan } = LANGS[lang];
    const cores = parts.map((p) => normCore(p.core));
    const out = [];
    let i = 0;
    while (i < rawTokens.length) {
      const m = matchAt(dict, maxSpan, cores, i);
      if (m) {
        const lead = parts[i].lead;
        const trail = parts[i + m.span - 1].trail;
        out.push({ text: lead + m.en + trail, matched: true });
        i += m.span;
      } else {
        out.push({ text: rawTokens[i], matched: false });
        i++;
      }
    }
    return out;
  }

  /* Full analysis. override = faction name to force, or null for auto-detect. */
  function analyze(LANGS, text, override) {
    const trimmed = (text || "").trim();
    if (!trimmed) return null;
    const rawTokens = trimmed.split(/\s+/);
    const parts = rawTokens.map(splitToken);
    const cores = parts.map((p) => normCore(p.core));

    let lang, count;
    if (override && LANGS[override]) {
      lang = override;
      count = matchedTokenCount(LANGS, override, cores);
    } else {
      const d = detect(LANGS, cores);
      lang = d.lang; count = d.count;
    }

    if (!lang) {
      return { lang: null, count: 0, total: rawTokens.length,
        segments: [{ text: trimmed, matched: false }] };
    }
    return { lang, count, total: rawTokens.length,
      segments: translateTokens(LANGS, lang, rawTokens, parts) };
  }

  window.NMSEngine = { PRIORITY, loadLangs, analyze };
})();
