// AinKotha — BdSL sign panel.
// Shows, automatically, WHY and WHICH NUMBER to call for each helpline in the assistant's reply.
// Sequence is built deterministically from the verified service data (never from LLM text):
//   [reason] -> [call] -> [digit] [digit] ...
// Layer 1 (always works): large visual cards with the reason + digits, auto-advancing.
// Layer 2 (optional): if a BdSL SiGML dataset is installed at /bdsl/dataset.json, the CWASA avatar
//   signs each step. Steps without a dataset entry fall back to the visual card.
(function () {
  const STEP_MS = 2600;           // visual-only step duration
  const SIGN_MS = 4800;           // per-sign duration when the avatar plays
  const DATASET_URL = "/data/Sections/dataset.json";
  const DATASET_BASE = "/data/Sections/";
  // Local copy first (put your CWASA folder at frontend/cwasa/), CDN as fallback.
  const CWASA_SOURCES = [
    { js: "https://vhg.cmp.uea.ac.uk/tech/jas/vhg2026/cwa/allcsa.js", css: "https://vhg.cmp.uea.ac.uk/tech/jas/vhg2026/cwa/cwasa.css" },
  ];

  let DIGIT_GLOSS = []; // exact SiGML gloss per digit (Numbers section has no English labels)
  let CALL_WORDS = ["call", "phone", "telephone"];
  const DIGIT_EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];
  const DIGIT_BN = ["০", "১", "২", "৩", "৪", "৫", "৬", "৭", "৮", "৯"];
  // category -> English dataset words to try for the "reason" sign
  const REASON_WORDS = {
    emergency: ["emergency", "danger", "help"],
    domestic_violence: ["violence", "beat", "family"],
    child_abuse: ["child", "abuse"],
    workplace_wage: ["salary", "job", "work"],
    cyber_harassment: ["mobile", "internet", "harassment"],
    consumer_rights: ["buy", "market", "shop"],
    legal_aid_general: ["law", "court", "help"],
  };

  let enabled = false;
  let dataset = null;             // Map english(lowercase) -> entry
  let datasetTried = false;
  let cwasaReady = null;          // Promise
  let runId = 0;                  // cancels stale playbacks
  let lastServices = [];
  const el = {};

  const bnDigits = (s) => String(s).replace(/\d/g, (d) => DIGIT_BN[+d]);

  function buildSteps(service, category, lang) {
    const en = lang === "en";
    const steps = [{
      kind: "reason",
      big: en ? service.name_en : service.name_bn,
      small: en ? "Why call" : "কেন কল করবেন",
      words: REASON_WORDS[category] || REASON_WORDS.legal_aid_general,
    }, {
      kind: "call",
      big: "📞",
      small: en ? "Call" : "কল করুন",
      words: CALL_WORDS,
    }];
    for (const ch of String(service.phone_number)) {
      if (/\d/.test(ch)) {
        steps.push({
          kind: "digit",
          big: en ? ch : DIGIT_BN[+ch],
          small: en ? "Number" : "নম্বর",
          digit: +ch,
          words: [DIGIT_EN[+ch], String(ch)],
        });
      }
    }
    steps.push({
      kind: "number",
      big: en ? service.phone_number : bnDigits(service.phone_number),
      small: (en ? service.name_en : service.name_bn) + (service.hours ? " · " + service.hours : ""),
      words: [],
    });
    return steps;
  }

  // ---------- dataset + CWASA (optional layer) ----------
  async function loadSignMap() {
    // optional editable word map: frontend/bdsl/signmap.json
    try {
      const r = await fetch("/bdsl/signmap.json");
      if (!r.ok) return;
      const m = await r.json();
      if (m.reasons) Object.assign(REASON_WORDS, m.reasons);
      if (Array.isArray(m.digits) && m.digits.length === 10) m.digits.forEach((w, i) => (DIGIT_EN[i] = w));
      if (Array.isArray(m.call)) CALL_WORDS = m.call;
      if (Array.isArray(m.digitGloss)) DIGIT_GLOSS = m.digitGloss;
    } catch (_) {}
  }

  async function loadDataset() {
    if (datasetTried) return dataset;
    datasetTried = true;
    await loadSignMap();
    try {
      const r = await fetch(DATASET_URL);
      if (!r.ok) return null;
      const raw = await r.json();
      const list = Array.isArray(raw) ? raw : raw.entries || [];
      const m = new Map();
      const cleanEn = (e) => {
        let t = String(e.english || e.gloss || "").trim();
        if (/[^ -~]/.test(t)) { const i = t.indexOf("_"); t = i >= 0 ? t.slice(i + 1) : ""; } // mojibake prefix
        return t.trim().toLowerCase();
      };
      for (const e of list) {
        if (!e.sigmlPath) continue;
        if (e.sectionEn === "Numbers" || e.category === "Numbers") m.set("gloss:" + e.gloss, e);
        const k = cleanEn(e);
        if (k && !m.has(k)) m.set(k, e);
      }
      dataset = m.size ? m : null;
    } catch (_) { dataset = null; }
    return dataset;
  }

  function sigmlUrl(entry) {
    const seg = (p) => String(p).split("/").filter(Boolean).map(encodeURIComponent).join("/");
    return DATASET_BASE + [seg(entry.datasetRoot || ""), seg(entry.sigmlPath)].filter(Boolean).join("/");
  }

  function findEntry(words, digit) {
    if (!dataset) return null;
    if (digit != null && DIGIT_GLOSS[digit]) {
      const g = dataset.get("gloss:" + DIGIT_GLOSS[digit]);
      if (g) return g;
    }
    for (const w of words) {
      const e = dataset.get(String(w).toLowerCase());
      if (e) return e;
    }
    return null;
  }

  function loadCwasa(initSigml) {
    if (cwasaReady) return cwasaReady;
    const tryLoad = (src) => new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet"; css.href = src.css;
      document.head.appendChild(css);
      const s = document.createElement("script");
      s.src = src.js;
      s.onload = () => {
        try {
          // The avatar .jar loads asynchronously; playing a SiGML before it finishes hits an
          // unnamed character ("avatars/.jar" request, then "reading '1'" crash). Wait for it.
          const avatarLoaded = new Promise((res) => {
            window.CWASA.addHook("avatarloaded", (evt) => { if (evt && evt.msg) res(); });
            setTimeout(res, 30000);
          });
          window.CWASA.init(initSigml ? { avSettings: [{ width: 260, height: 300, avList: "avsfull", initAv: "luna", initSiGMLURL: initSigml }] } : undefined); // async: avatar panels exist only once CWASA.ready resolves
          Promise.resolve(window.CWASA.ready).then(() => avatarLoaded).then(() => resolve(window.CWASA), reject);
        } catch (e) { reject(e); }
      };
      s.onerror = () => { s.remove(); css.remove(); reject(new Error("CWASA unavailable: " + src.js)); };
      document.head.appendChild(s);
    });
    cwasaReady = CWASA_SOURCES.slice(1).reduce((p, src) => p.catch(() => tryLoad(src)), tryLoad(CWASA_SOURCES[0]));
    cwasaReady.catch(() => {});
    return cwasaReady;
  }

  // ---------- rendering ----------
  function show(step, idx, total) {
    el.big.textContent = step.big;
    el.big.className = "sign-big sign-" + step.kind;
    el.small.textContent = step.small;
    el.dots.innerHTML = "";
    for (let i = 0; i < total; i++) {
      const d = document.createElement("span");
      if (i === idx) d.className = "on";
      el.dots.appendChild(d);
    }
  }

  let listServices = [];
  function renderList(services, lang) {
    listServices = services;
    el.list.innerHTML = "";
    services.forEach((svc, i) => {
      const li = document.createElement("li");
      const n = document.createElement("span");
      n.textContent = lang === "en" ? svc.name_en : svc.name_bn;
      const b = document.createElement("b");
      b.textContent = lang === "en" ? svc.phone_number : bnDigits(svc.phone_number);
      li.append(n, b);
      li.addEventListener("click", () => play([svc], null, lang, false, true));
      li.dataset.i = i;
      el.list.appendChild(li);
    });
  }
  function markList(svc) {
    const i = listServices.indexOf(svc);
    [...el.list.children].forEach((li, k) => li.classList.toggle("on", k === i));
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function play(services, category, lang, loop, force) {
    const my = ++runId;
    if ((!enabled && !loop && !force) || !services || !services.length) return;
    el.panel.classList.remove("hidden");
    await loadDataset();
    let cwasa = null;
    if (dataset) {
      el.avatarWrap.classList.remove("hidden"); // CWASA must init on a visible container
      try {
        const first = findEntry([], 1); // any real sign: CWASA fails on an empty initial SiGML
        cwasa = await loadCwasa(first ? location.origin + sigmlUrl(first) : null);
      } catch (_) { cwasa = null; }
    }
    el.avatarWrap.classList.toggle("hidden", !cwasa);

    const list = loop || force ? services : services.slice(0, 2);
    if (!force) renderList(services, lang);
    do {
    for (const svc of list) {
      const cat = loop || !category ? ((svc.categories || []).includes("emergency") ? "emergency" : (svc.categories || [])[0]) : category;
      const steps = buildSteps(svc, cat, lang);
      markList(svc);
      for (let i = 0; i < steps.length; i++) {
        if (my !== runId) return;
        show(steps[i], i, steps.length);
        const entry = cwasa ? findEntry(steps[i].words, steps[i].digit) : null;
        if (entry) {
          // URL must be absolute: CWASA resolves relative URLs against its own (CDN) base
          try { cwasa.playSiGMLURL(location.origin + sigmlUrl(entry), 0); } catch (_) {}
          await sleep(SIGN_MS);
        } else {
          await sleep(steps[i].kind === "number" ? STEP_MS * 1.6 : STEP_MS);
        }
      }
      if (loop) await sleep(1500);
    }
    } while (loop && my === runId);
  }

  // ---------- standalone sign section: loops every helpline until closed ----------
  let sectionOpen = false;
  async function openSection(lang) {
    sectionOpen = true;
    ["consentScreen", "callScreen", "summaryScreen"].forEach((id) => document.getElementById(id).classList.add("hidden"));
    el.close.classList.remove("hidden");
    el.panel.classList.remove("hidden");
    show({ kind: "reason", big: "…", small: lang === "en" ? "Loading" : "লোড হচ্ছে" }, 0, 1);
    let services = [];
    try { services = await (await fetch("/api/services")).json(); } catch (_) {}
    if (!sectionOpen) return;
    if (!services.length) { show({ kind: "reason", big: "৯৯৯", small: "জরুরি সেবা" }, 0, 1); return; }
    services.sort((a, b) => (b.phone_number === "999") - (a.phone_number === "999")); // 999 first
    play(services, null, lang, true);
  }
  function closeSection() {
    sectionOpen = false; runId++;
    el.close.classList.add("hidden");
    el.panel.classList.add("hidden");
    document.getElementById("consentScreen").classList.remove("hidden");
  }

  // ---------- public API ----------
  function onReply(data, lang) {
    if (data.services && data.services.length) lastServices = data.services;
    if (data.is_emergency) {
      lastServices = [{
        name_bn: "জাতীয় জরুরি সেবা", name_en: "National Emergency Service",
        phone_number: "999", hours: "24/7",
      }];
      play(lastServices, "emergency", lang);
    } else if (data.services && data.services.length) {
      play(data.services, data.category, lang);
    }
  }

  function setEnabled(on) {
    enabled = on;
    el.toggle.classList.toggle("active", on);
    el.toggle.setAttribute("aria-pressed", String(on));
    if (!on) { runId++; el.panel.classList.add("hidden"); }
    else if (lastServices.length) play(lastServices, null, document.documentElement.lang === "en" ? "en" : "bn");
    try { localStorage.setItem("ainkotha_sign", on ? "1" : "0"); } catch (_) {}
  }

  function init() {
    el.toggle = document.getElementById("signBtn");
    el.panel = document.getElementById("signPanel");
    el.big = document.getElementById("signBig");
    el.small = document.getElementById("signSmall");
    el.dots = document.getElementById("signDots");
    el.close = document.getElementById("signClose");
    el.avatarWrap = document.getElementById("signAvatarWrap");
    el.list = document.getElementById("signList");
    if (!el.toggle || !el.panel) return;
    el.toggle.addEventListener("click", () => setEnabled(!enabled));
    document.getElementById("signReplay").addEventListener("click", () => {
      if (sectionOpen) openSection(window.AinKothaLang ? window.AinKothaLang() : "bn");
      else if (lastServices.length) play(lastServices, null, window.AinKothaLang ? window.AinKothaLang() : "bn");
    });
    el.close.addEventListener("click", closeSection);
    const open = document.getElementById("openSignSection");
    if (open) open.addEventListener("click", (e) => { e.preventDefault(); openSection(window.AinKothaLang ? window.AinKothaLang() : "bn"); });
    try { if (localStorage.getItem("ainkotha_sign") === "1") setEnabled(true); } catch (_) {}
  }

  window.AinKothaSign = { onReply, stop() { runId++; }, isEnabled: () => enabled };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
