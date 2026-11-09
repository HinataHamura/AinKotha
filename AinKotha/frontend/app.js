// AinKotha frontend — voice call UI wired to /api/chat (FR-1, FR-2, FR-8)
const API_URL = "/api/chat";
const SESSION_ID = crypto.randomUUID();
let SILENCE_TIMEOUT_MS = 60000; // FR-1.5 — overridden by /api/config on load

fetch("/api/config")
  .then((r) => r.json())
  .then((cfg) => {
    if (cfg && cfg.silence_timeout_seconds > 0) {
      SILENCE_TIMEOUT_MS = cfg.silence_timeout_seconds * 1000;
    }
  })
  .catch(() => {});

const $ = (id) => document.getElementById(id);

const consentScreen = $("consentScreen");
const callScreen = $("callScreen");
const summaryScreen = $("summaryScreen");
const emergencyBanner = $("emergencyBanner");
const transcriptBox = $("transcriptBox");
const orb = $("orb");
const callStatus = $("callStatus");
const micState = $("micState");
const textFallback = $("textFallback");
const textInput = $("textInput");
const emergencyStatus = $("emergencyStatus");

let recognition = null;
let recognitionActive = false;
let recognitionStarting = false;
let assistantSpeaking = false;
let ignoreSpeechUntil = 0;
let spokenText = "";
let finishCurrentSpeech = null;
let speechGeneration = 0;
let muted = false;
let silenceTimer = null;
let callLog = []; // {category, laws, services} accumulated for summary
let usingTextMode = false;
let currentAudio = null;
let language = "bn";
window.AinKothaLang = () => language;

// ---------- Consent language toggle (FR-2.6) ----------
const CONSENT_TEXT = {
  bn: {
    title: "শুরু করার আগে",
    items: [
      "আমি একজন <strong>আইনজীবী নই</strong> — এটি একটি AI সহকারী, শুধু সাধারণ তথ্য দেয়।",
      "আপনার <strong>কণ্ঠ রেকর্ড করা হবে না।</strong>",
      "জরুরি বিপদে থাকলে সরাসরি <strong>৯৯৯</strong> নম্বরে কল করুন।",
      "থানা খুঁজতে আপনার GPS অবস্থান ব্যবহার হবে; এটি আমাদের সার্ভারে সংরক্ষণ হবে না। মানচিত্র দেখাতে OpenStreetMap থেকে map tile লোড হবে।",
      "শুধু নাম/ফোন নম্বরবিহীন বেনামি তথ্য (ক্যাটাগরি, সময়) যাচাইয়ের জন্য রাখা হতে পারে।",
    ],
    agree: "আমি বুঝেছি এবং সম্মত আছি",
    start: "কল শুরু করুন",
    textMode: "ভয়েসের বদলে টেক্সটে লিখতে চাই",
    langBtn: "English",
  },
  en: {
    title: "Before you start",
    items: [
      "I am <strong>not a lawyer</strong> — this is an AI assistant that provides general information only.",
      "Your <strong>voice will not be recorded.</strong>",
      "If you are in immediate danger, call <strong>999</strong> directly.",
      "Your GPS location is used to find a police station and is not stored on our server. Map tiles load from OpenStreetMap.",
      "Only anonymous data (category, timestamp) may be kept for evaluation — no names or phone numbers.",
    ],
    agree: "I understand and agree",
    start: "Start Call",
    textMode: "Use text instead of voice",
    langBtn: "বাংলা",
  },
};

function applyConsentLanguage(lang) {
  const t = CONSENT_TEXT[lang];
  $("consentTitle").textContent = t.title;
  const list = $("consentList");
  list.innerHTML = t.items.map((item) => `<li>${item}</li>`).join("");
  $("consentAgreeLabel").innerHTML = t.agree;
  $("startCallLabel").textContent = t.start;
  $("useTextInstead").textContent = t.textMode;
  $("consentLangBtn").textContent = t.langBtn;
}

$("consentLangBtn").addEventListener("click", () => {
  language = language === "bn" ? "en" : "bn";
  $("languageBtn").textContent = language === "bn" ? "English" : "বাংলা";
  applyConsentLanguage(language);
});

// ---------- Consent gating ----------
$("consentCheck").addEventListener("change", (e) => {
  $("startCallBtn").disabled = !e.target.checked;
});

$("startCallBtn").addEventListener("click", () => startCall(false));
$("useTextInstead").addEventListener("click", (e) => {
  e.preventDefault();
  if (!$("consentCheck").checked) {
    $("consentCheck").checked = true;
    $("startCallBtn").disabled = false;
  }
  startCall(true);
});

function startCall(textMode) {
  usingTextMode = textMode;
  consentScreen.classList.add("hidden");
  callScreen.classList.remove("hidden");
  summaryScreen.classList.add("hidden");
  transcriptBox.innerHTML = "";
  callLog = [];
  // FR-3.3: show emergency banner throughout the entire call
  emergencyBanner.classList.remove("hidden");

  const hasVoice = !textMode && setupRecognition();
  if (!hasVoice) {
    textFallback.classList.remove("hidden");
    micState.textContent = "⌨️ টেক্সটে লিখুন";
    greet(false);
  } else {
    textFallback.classList.add("hidden");
    // Greet first, start mic only AFTER TTS finishes so bot voice isn't picked up as user input
    greet(true).then(() => {
      if (!muted) startRecognition();
    });
  }
  resetSilenceTimer();
}

function greet(waitForAudio = false) {
  const text = language === "en"
    ? "Hello. I can share general information about laws and helplines in Bangladesh. I am not a lawyer. Please tell me your problem."
    : "আমি AinKotha — আইনি তথ্য ও হেল্পলাইন সম্পর্কে সাধারণ তথ্য দিতে পারি। আমি একজন আইনজীবী নই। আপনার সমস্যা বলুন।";
  addBubble("bot", text);
  if (waitForAudio) return speakAndWait(text);
  speak(text);
  return Promise.resolve();
}

// ---------- Web Speech API (STT) ----------
function setupRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;
  recognition = new SR();
  recognition.lang = "bn-BD";
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.onresult = (event) => {
    if (Date.now() < ignoreSpeechUntil) return;
    resetSilenceTimer();
    let finalText = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) finalText += event.results[i][0].transcript;
    }
    if (finalText.trim()) {
      const text = finalText.trim();
      if (assistantSpeaking && isAssistantEcho(text)) return;
      // Barge-in: stop assistant speaking when the user says something different.
      if (assistantSpeaking) stopAudio();
      handleUserTranscript(text);
    }
  };
  recognition.onerror = () => {};
  recognition.onend = () => {
    recognitionStarting = false;
    if (recognitionActive && !muted) startRecognition();
  };
  return true;
}

function startRecognition() {
  if (!recognition || recognitionStarting || recognitionActive) return;
  recognitionStarting = true;
  recognitionActive = true;
  try {
    recognition.start();
  } catch (e) {
    recognitionStarting = false;
    recognitionActive = false;
    return;
  }
  orb.classList.add("listening");
  callStatus.textContent = "সংযোগ হয়েছে — কথা বলুন";
  micState.textContent = "🎙️ শুনছি...";
}

function stopRecognition() {
  recognitionActive = false;
  recognitionStarting = false;
  if (recognition) { try { recognition.stop(); } catch (e) {} }
  orb.classList.remove("listening");
}

$("muteBtn").addEventListener("click", () => {
  muted = !muted;
  $("muteBtn").classList.toggle("active", muted);
  if (muted) { stopRecognition(); micState.textContent = "🔇 মাইক বন্ধ"; }
  else { startRecognition(); }
});

$("toggleTextBtn").addEventListener("click", () => {
  textFallback.classList.toggle("hidden");
});

$("sendTextBtn").addEventListener("click", sendTextInput);
textInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendTextInput(); });

function sendTextInput() {
  const val = textInput.value.trim();
  if (!val) return;
  textInput.value = "";
  resetSilenceTimer();
  handleUserTranscript(val);
}

// ---------- Silence timeout (FR-1.5) ----------
function resetSilenceTimer() {
  clearTimeout(silenceTimer);
  silenceTimer = setTimeout(() => {
    if (assistantSpeaking) {
      resetSilenceTimer();
      return;
    }
    const text = language === "en"
      ? "I did not hear a response, so I am ending the call. Please call again if needed. Thank you."
      : "কোনো সাড়া পাচ্ছি না, তাই কলটি শেষ করছি। প্রয়োজন হলে আবার কল করবেন। ধন্যবাদ।";
    addBubble("bot", text);
    speak(text);
    setTimeout(endCall, 1800);
  }, SILENCE_TIMEOUT_MS);
}

// ---------- TTS ----------
function stopAudio(cancelSpeech = true) {
  if (cancelSpeech) speechGeneration += 1;
  const audio = currentAudio;
  currentAudio = null;
  if (audio) {
    audio.pause();
    URL.revokeObjectURL(audio.src);
  }
  assistantSpeaking = false;
  spokenText = "";
  orb.classList.remove("speaking");
  micState.textContent = muted ? "🔇 মাইক বন্ধ" : "🎙️ শুনছি...";
  ignoreSpeechUntil = Date.now() + 300;
  if (finishCurrentSpeech) {
    const finish = finishCurrentSpeech;
    finishCurrentSpeech = null;
    finish();
  }
}

function speakAndWait(text, slow = false) {
  return new Promise((resolve) => {
    speak(text, slow).then(resolve).catch(resolve);
  });
}

async function speak(text, slow = false) {
  const generation = ++speechGeneration;
  assistantSpeaking = true;
  spokenText = text;
  resetSilenceTimer();
  if (!muted && !recognitionActive) startRecognition();
  orb.classList.add("speaking");
  orb.classList.remove("listening");
  micState.textContent = "🔊 বলছি...";

  try {
    // Speak sentence by sentence: the first piece starts quickly while the next one downloads.
    const pieces = splitForTts(text);
    let next = fetchTtsAudio(pieces[0], slow);
    for (let i = 0; i < pieces.length; i++) {
      const audioUrl = await next;
      if (i + 1 < pieces.length) next = fetchTtsAudio(pieces[i + 1], slow);
      if (generation !== speechGeneration) {
        URL.revokeObjectURL(audioUrl);
        return;
      }
      await playTtsUrl(audioUrl);
      if (generation !== speechGeneration) return;
    }
    orb.classList.remove("speaking");
    micState.textContent = muted ? "🔇 মাইক বন্ধ" : "🎙️ শুনছি...";
    assistantSpeaking = false;
    spokenText = "";
    ignoreSpeechUntil = Date.now() + 500;
    resetSilenceTimer();
  } catch (err) {
    if (generation !== speechGeneration) return;
    console.warn("Bangla TTS unavailable:", err);
    orb.classList.remove("speaking");
    micState.textContent = muted ? "🔇 মাইক বন্ধ" : "🎙️ শুনছি...";
    assistantSpeaking = false;
    spokenText = "";
    ignoreSpeechUntil = Date.now() + 500;
    resetSilenceTimer();
  }
}

// Split on sentence/clause punctuation and pack into pieces of at most `limit` characters.
function splitForTts(text, limit = 90) {
  const parts = text.split(/(?<=[।.?!;,])\s+|\s+—\s+/u).map((p) => p.trim()).filter(Boolean);
  const pieces = [];
  for (let part of parts) {
    while (part.length > limit) {
      let cut = part.lastIndexOf(" ", limit);
      if (cut <= 0) cut = limit;
      pieces.push(part.slice(0, cut).trim());
      part = part.slice(cut).trim();
    }
    if (pieces.length && part && pieces[pieces.length - 1].length + 1 + part.length <= limit) {
      pieces[pieces.length - 1] += " " + part;
    } else if (part) {
      pieces.push(part);
    }
  }
  return pieces.length ? pieces : [text];
}

async function fetchTtsAudio(text, slow) {
  const res = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, language, slow }),
  });
  if (!res.ok) throw new Error(`TTS request failed: ${res.status}`);
  return URL.createObjectURL(await res.blob());
}

// Play one audio piece; resolves when it ends, fails, or stopAudio() interrupts it.
function playTtsUrl(audioUrl) {
  return new Promise((resolve) => {
    const audio = new Audio(audioUrl);
    currentAudio = audio;
    finishCurrentSpeech = resolve;
    const done = () => {
      URL.revokeObjectURL(audioUrl);
      if (currentAudio === audio) currentAudio = null;
      if (finishCurrentSpeech === resolve) finishCurrentSpeech = null;
      resolve();
    };
    audio.onended = done;
    audio.onerror = done;
    audio.play().catch(done);
  });
}

function isAssistantEcho(text) {
  if (!assistantSpeaking) return false;
  const normalize = (value) => value.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
  const heard = normalize(text);
  const spoken = normalize(spokenText);
  return heard.length < 3 || (spoken.length > 0 && (spoken.includes(heard) || heard.includes(spoken)));
}

// FR-7.3: detect "আস্তে বলুন" / "repeat slowly" requests
const SLOW_REPEAT_PATTERNS_BN = ["আস্তে বল", "ধীরে বল", "আবার বল", "নম্বরগুলো আবার", "আবার একটু ধীরে"];
const SLOW_REPEAT_PATTERNS_EN = ["repeat slowly", "say again slowly", "numbers again", "slowly again", "say the numbers"];

function isSlowRepeatRequest(text) {
  const t = text.toLowerCase();
  const patterns = language === "en" ? SLOW_REPEAT_PATTERNS_EN : SLOW_REPEAT_PATTERNS_BN;
  return patterns.some((p) => t.includes(p));
}

// Extract phone numbers from the last bot bubble for slow repeat
function getLastServiceNumbers() {
  const bubbles = transcriptBox.querySelectorAll(".bot");
  if (!bubbles.length) return null;
  const last = bubbles[bubbles.length - 1].textContent;
  // find all sequences that look like phone numbers (3-5 digit short codes or longer)
  const nums = last.match(/\b\d{3,11}\b/g);
  return nums ? [...new Set(nums)].join(", ") : null;
}

// ---------- Transcript UI ----------
function addBubble(who, text, category, confidence) {
  const div = document.createElement("div");
  div.className = who;
  const label = who === "me" ? "আপনি" : "AinKotha";
  let meta = "";
  if (who === "bot" && category && category !== "unknown" && category !== "emergency" && confidence > 0) {
    const pct = Math.round(confidence * 100);
    meta = ` <span class="confidence-badge">${category.replaceAll("_", " ")} ${pct}%</span>`;
  }
  div.innerHTML = `<b>${label}${meta}</b>${escapeHtml(text)}`;
  transcriptBox.appendChild(div);
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- Nearest police station ----------
const thanaButtons = [$("thanaBtn"), $("thanaQuickBtn")];
const thanaPanel = $("thanaPanel");
const thanaStatus = $("thanaStatus");
const thanaDetails = $("thanaDetails");
const thanaPhone = $("thanaPhone");
const thanaMap = $("thanaMap");
const thanaMapFallback = $("thanaMapFallback");
let nearestThanaPhone = "";

thanaButtons.forEach((button) => button.addEventListener("click", findNearestThana));

function findNearestThana() {
  thanaPanel.hidden = false;
  thanaDetails.hidden = true;
  thanaStatus.textContent = "";
  if (!navigator.geolocation) {
    showThanaError("আপনার ব্রাউজারে অবস্থান নির্ণয় সুবিধা নেই। জরুরি প্রয়োজনে ৯৯৯-এ কল করুন।");
    return;
  }
  setThanaButtonsDisabled(true);
  thanaStatus.textContent = "আপনার অবস্থান নির্ণয় করা হচ্ছে…";
  try {
    navigator.geolocation.getCurrentPosition(loadNearestThana, (error) => {
      const messages = {
        1: "অবস্থান শেয়ার করা হয়নি। জরুরি প্রয়োজনে ৯৯৯-এ কল করুন।",
        2: "GPS সংকেত পাওয়া যাচ্ছে না। পরে আবার চেষ্টা করুন।",
        3: "অবস্থান নির্ণয় করতে সময় লাগছে। আবার চেষ্টা করুন।",
      };
      showThanaError(messages[error.code] || "অবস্থান নির্ণয় করা যায়নি। জরুরি প্রয়োজনে ৯৯৯-এ কল করুন।");
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  } catch (error) {
    console.error("Could not request the user's location:", error);
    showThanaError("অবস্থান নির্ণয় করা যায়নি। জরুরি প্রয়োজনে ৯৯৯-এ কল করুন।");
  }
}

async function loadNearestThana(position) {
  const { latitude, longitude } = position.coords;
  try {
    const params = new URLSearchParams({ lat: String(latitude), lng: String(longitude) });
    const response = await fetch(`/api/nearest-thana?${params}`);
    if (response.status === 404) {
      showThanaError("এই এলাকার থানার তথ্য এখনো নেই। বর্তমানে ঢাকা ও রাজশাহীর কিছু এলাকার তথ্য আছে। জরুরি প্রয়োজনে ৯৯৯-এ কল করুন।");
      return;
    }
    if (!response.ok) throw new Error(`Nearest thana request failed: ${response.status}`);
    const data = await response.json();
    const thana = data.thana;
    thanaDetails.hidden = false;
    thanaStatus.textContent = "";
    $("thanaName").textContent = `${thana.name_bn} (${thana.name_en})`;
    $("thanaDistance").textContent = `আনুমানিক দূরত্ব: ${Number(data.distance_km).toFixed(1)} কিমি (সরলরেখায়)`;
    $("thanaWarning").hidden = Boolean(thana.verified);
    nearestThanaPhone = thana.phone || "";
    if (nearestThanaPhone) {
      thanaPhone.textContent = nearestThanaPhone;
      thanaPhone.href = `tel:${nearestThanaPhone}`;
      thanaPhone.removeAttribute("aria-label");
    } else {
      thanaPhone.textContent = "থানার নম্বর যাচাই করা হয়নি — জরুরি প্রয়োজনে ৯৯৯";
      thanaPhone.href = "tel:999";
      thanaPhone.setAttribute("aria-label", "জরুরি নম্বর ৯৯৯");
    }

    renderThanaMap(latitude, longitude, thana.lat, thana.lng);
    const routeParams = new URLSearchParams({
      api: "1",
      origin: `${latitude},${longitude}`,
      destination: `${thana.lat},${thana.lng}`,
    });
    $("thanaRouteLink").href = `https://www.google.com/maps/dir/?${routeParams}`;
  } catch (error) {
    console.error("Nearest thana lookup failed:", error);
    showThanaError("থানার তথ্য পাওয়া যায়নি। পরে চেষ্টা করুন; জরুরি প্রয়োজনে ৯৯৯-এ কল করুন।");
  } finally {
    setThanaButtonsDisabled(false);
  }
}

function renderThanaMap(userLat, userLng, thanaLat, thanaLng) {
  const width = 400;
  const height = 200;
  const tileSize = 256;
  const toWorldPixel = (lat, lng, zoom) => {
    const worldSize = tileSize * (2 ** zoom);
    const latitude = Math.max(-85.05112878, Math.min(85.05112878, lat));
    const sinLatitude = Math.sin(latitude * Math.PI / 180);
    return {
      x: (lng + 180) / 360 * worldSize,
      y: (0.5 - Math.log((1 + sinLatitude) / (1 - sinLatitude)) / (4 * Math.PI)) * worldSize,
    };
  };
  let zoom = 10;
  for (let candidate = 15; candidate >= 10; candidate--) {
    const userAtZoom = toWorldPixel(userLat, userLng, candidate);
    const stationAtZoom = toWorldPixel(thanaLat, thanaLng, candidate);
    if (Math.abs(userAtZoom.x - stationAtZoom.x) <= width - 80
      && Math.abs(userAtZoom.y - stationAtZoom.y) <= height - 60) {
      zoom = candidate;
      break;
    }
  }
  const user = toWorldPixel(userLat, userLng, zoom);
  const station = toWorldPixel(thanaLat, thanaLng, zoom);
  const centerX = (user.x + station.x) / 2;
  const centerY = (user.y + station.y) / 2;
  const originX = centerX - width / 2;
  const originY = centerY - height / 2;
  const startTileX = Math.floor(originX / tileSize);
  const endTileX = Math.floor((originX + width) / tileSize);
  const startTileY = Math.floor(originY / tileSize);
  const endTileY = Math.floor((originY + height) / tileSize);
  const fragment = document.createDocumentFragment();
  let pendingTiles = 0;
  let failedTile = false;

  const updateMapFallback = () => {
    if (pendingTiles === 0) {
      thanaMapFallback.hidden = !failedTile;
    }
  };

  for (let tileY = startTileY; tileY <= endTileY; tileY++) {
    if (tileY < 0 || tileY >= 2 ** zoom) continue;
    for (let tileX = startTileX; tileX <= endTileX; tileX++) {
      const tile = document.createElement("img");
      tile.alt = "";
      tile.draggable = false;
      tile.className = "thana-map-tile";
      tile.style.left = `${tileX * tileSize - originX}px`;
      tile.style.top = `${tileY * tileSize - originY}px`;
      tile.addEventListener("load", () => {
        pendingTiles--;
        updateMapFallback();
      }, { once: true });
      tile.addEventListener("error", () => {
        failedTile = true;
        tile.remove();
        pendingTiles--;
        updateMapFallback();
      }, { once: true });
      pendingTiles++;
      tile.src = `https://tile.openstreetmap.org/${zoom}/${((tileX % (2 ** zoom)) + 2 ** zoom) % (2 ** zoom)}/${tileY}.png`;
      fragment.appendChild(tile);
    }
  }

  thanaMap.replaceChildren(fragment);
  thanaMapFallback.hidden = true;
  const addMarker = (point, label, type) => {
    const marker = document.createElement("span");
    marker.className = `thana-map-marker ${type}`;
    marker.style.left = `${point.x - originX}px`;
    marker.style.top = `${point.y - originY}px`;
    marker.textContent = label;
    thanaMap.appendChild(marker);
  };
  const routeLine = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  routeLine.setAttribute("class", "thana-map-route-line");
  routeLine.setAttribute("viewBox", `0 0 ${width} ${height}`);
  routeLine.setAttribute("aria-hidden", "true");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.setAttribute("x1", String(user.x - originX));
  line.setAttribute("y1", String(user.y - originY));
  line.setAttribute("x2", String(station.x - originX));
  line.setAttribute("y2", String(station.y - originY));
  routeLine.appendChild(line);
  thanaMap.appendChild(routeLine);
  addMarker(user, "আপনি", "user");
  addMarker(station, "থানা", "station");
  updateMapFallback();
}

function showThanaError(message) {
  thanaStatus.textContent = message;
  thanaDetails.hidden = true;
  setThanaButtonsDisabled(false);
}

function setThanaButtonsDisabled(disabled) {
  thanaButtons.forEach((button) => { button.disabled = disabled; });
}

// Close thana panel
$("thanaPanelClose").addEventListener("click", () => {
  $("thanaPanel").hidden = true;
});

$("thanaCopyBtn").addEventListener("click", async () => {
  if (!nearestThanaPhone) {
    thanaStatus.textContent = "থানার ফোন নম্বর যাচাই করা হয়নি। জরুরি প্রয়োজনে ৯৯৯-এ কল করুন।";
    return;
  }
  try {
    await navigator.clipboard.writeText(nearestThanaPhone);
    thanaStatus.textContent = "ফোন নম্বর কপি হয়েছে।";
  } catch (error) {
    console.error("Could not copy thana phone number:", error);
    thanaStatus.textContent = "নম্বর কপি করা যায়নি; নম্বরটি নির্বাচন করে কপি করুন।";
  }
});

// ---------- Backend call ----------
async function handleUserTranscript(text) {
  addBubble("me", text);

  // FR-7.3: slow repeat request — speak last numbers slowly without calling backend
  if (isSlowRepeatRequest(text)) {
    const nums = getLastServiceNumbers();
    const reply = nums
      ? (language === "en"
          ? `The numbers are: ${nums}. I will say them slowly.`
          : `নম্বরগুলো হলো: ${nums}। আমি ধীরে বলছি।`)
      : (language === "en" ? "I will repeat the last reply slowly." : "আগের উত্তরটি ধীরে বলছি।");
    addBubble("bot", reply);
    speak(reply, true);
    return;
  }

  callStatus.textContent = "ভাবছি...";
  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: SESSION_ID, transcript: text, language }),
    });
    const data = await res.json();
    addBubble("bot", data.reply_text, data.category, data.confidence);
    speak(data.reply_text);
    callStatus.textContent = "সংযোগ হয়েছে — কথা বলুন";
    if (window.AinKothaSign) window.AinKothaSign.onReply(data, language);

    if (data.is_emergency) {
      emergencyBanner.classList.remove("hidden");
      emergencyStatus.textContent = language === "en"
        ? "Immediate danger: call 999 now."
        : "জরুরি বিপদে এখনই ৯৯৯ নম্বরে কল করুন।";
      emergencyStatus.classList.remove("hidden");
    }
    if (data.category && data.category !== "unknown" && data.category !== "emergency") {
      callLog.push({ category: data.category, laws: data.laws, services: data.services });
    }
  } catch (err) {
    const text2 = "দুঃখিত, সংযোগে সমস্যা হচ্ছে। একটু পরে আবার চেষ্টা করুন।";
    addBubble("bot", text2);
    callStatus.textContent = "সংযোগ ত্রুটি";
  }
}

// ---------- End call / summary ----------
$("endCallBtn").addEventListener("click", endCall);

function endCall() {
  if (window.AinKothaSign) window.AinKothaSign.stop();
  const sp = $("signPanel"); if (sp) sp.classList.add("hidden");
  clearTimeout(silenceTimer);
  stopRecognition();
  stopAudio();
  callScreen.classList.add("hidden");
  renderSummary();
  summaryScreen.classList.remove("hidden");
}

function renderSummary() {
  const sumCategory = $("sumCategory");
  const sumLaws = $("sumLaws");
  const sumServices = $("sumServices");
  sumLaws.innerHTML = "";
  sumServices.innerHTML = "";

  if (callLog.length === 0) {
    sumCategory.textContent = "নির্দিষ্ট করা যায়নি";
    $("sumLawsWrap").classList.add("hidden");
    $("sumServicesWrap").classList.add("hidden");
    return;
  }
  $("sumLawsWrap").classList.remove("hidden");
  $("sumServicesWrap").classList.remove("hidden");

  const last = callLog[callLog.length - 1];
  sumCategory.textContent = last.category.replaceAll("_", " ");

  const seenLaw = new Set();
  const seenSvc = new Set();
  callLog.forEach((entry) => {
    (entry.laws || []).forEach((l) => {
      if (seenLaw.has(l.law_id)) return;
      seenLaw.add(l.law_id);
      const chip = document.createElement("div");
      chip.className = "chip";
      chip.innerHTML = `<b>${l.name_bn} (${l.name_en})</b>${l.summary_bn}`;
      sumLaws.appendChild(chip);
    });
    (entry.services || []).forEach((s) => {
      if (seenSvc.has(s.service_id)) return;
      seenSvc.add(s.service_id);
      const row = document.createElement("div");
      row.className = "service-item";
      const detailParts = [];
      if (s.description_bn) detailParts.push(s.description_bn);
      if (s.hours) detailParts.push(s.hours);
      const detailHtml = detailParts.length
        ? `<div class="service-detail">${escapeHtml(detailParts.join(" · "))}</div>`
        : "";
      row.innerHTML = `
        <div class="service-item-row">
          <span>${escapeHtml(s.name_bn)}</span>
          <span><a href="tel:${s.phone_number}">${s.phone_number}</a>${detailHtml ? ' <span class="service-toggle">▼</span>' : ""}</span>
        </div>${detailHtml}`;
      if (detailHtml) {
        row.addEventListener("click", () => row.classList.toggle("expanded"));
      }
      sumServices.appendChild(row);
    });
  });
}

$("copySummaryBtn").addEventListener("click", () => {
  const text = transcriptBox.innerText;
  navigator.clipboard.writeText(text).then(() => {
    $("copySummaryBtn").textContent = "কপি হয়েছে ✓";
    setTimeout(() => ($("copySummaryBtn").textContent = "সারাংশ কপি করুন"), 1500);
  });
});

$("newCallBtn").addEventListener("click", () => {
  summaryScreen.classList.add("hidden");
  emergencyBanner.classList.add("hidden");
  consentScreen.classList.remove("hidden");
});

$("helpBtn").addEventListener("click", () => {
  // FR-7.3: helpBtn always speaks numbers slowly so user can note them
  const text = language === "en"
    ? "Emergency service 999. Violence against women and children helpline 109. National legal aid 16430. Child helpline 1098."
    : "জরুরি সেবা ৯৯৯। নারী ও শিশু নির্যাতন হেল্পলাইন ১০৯। জাতীয় আইনগত সহায়তা ১৬৪৩০। চাইল্ড হেল্পলাইন ১০৯৮।";
  addBubble("bot", text);
  speak(text, true); // slow=true so numbers are clearly heard
});

$("languageBtn").addEventListener("click", () => {
  language = language === "bn" ? "en" : "bn";
  $("languageBtn").textContent = language === "bn" ? "English" : "বাংলা";
});
