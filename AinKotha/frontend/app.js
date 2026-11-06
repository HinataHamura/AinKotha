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
let muted = false;
let silenceTimer = null;
let callLog = []; // {category, laws, services} accumulated for summary
let usingTextMode = false;
let currentAudio = null;
let language = "bn";

// ---------- Consent language toggle (FR-2.6) ----------
const CONSENT_TEXT = {
  bn: {
    title: "শুরু করার আগে",
    items: [
      "আমি একজন <strong>আইনজীবী নই</strong> — এটি একটি AI সহকারী, শুধু সাধারণ তথ্য দেয়।",
      "আপনার <strong>কণ্ঠ রেকর্ড করা হবে না।</strong>",
      "জরুরি বিপদে থাকলে সরাসরি <strong>৯৯৯</strong> নম্বরে কল করুন।",
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
    if (assistantSpeaking || Date.now() < ignoreSpeechUntil) return;
    resetSilenceTimer();
    let finalText = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) finalText += event.results[i][0].transcript;
    }
    if (finalText.trim()) {
      // barge-in: stop assistant speaking (FR-2.3)
      stopAudio();
      handleUserTranscript(finalText.trim());
    }
  };
  recognition.onerror = () => {};
  recognition.onend = () => {
    recognitionStarting = false;
    if (!assistantSpeaking && recognitionActive && !muted) startRecognition();
  };
  return true;
}

function startRecognition() {
  if (!recognition || assistantSpeaking || recognitionStarting || recognitionActive) return;
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
    const text = language === "en"
      ? "I did not hear a response, so I am ending the call. Please call again if needed. Thank you."
      : "কোনো সাড়া পাচ্ছি না, তাই কলটি শেষ করছি। প্রয়োজন হলে আবার কল করবেন। ধন্যবাদ।";
    addBubble("bot", text);
    speak(text);
    setTimeout(endCall, 1800);
  }, SILENCE_TIMEOUT_MS);
}

// ---------- TTS ----------
function stopAudio() {
  if (!currentAudio) return;
  currentAudio.pause();
  URL.revokeObjectURL(currentAudio.src);
  currentAudio = null;
}

function speakAndWait(text, slow = false) {
  return new Promise((resolve) => {
    speak(text, slow).then(resolve).catch(resolve);
  });
}

async function speak(text, slow = false) {
  const resumeRecognition = recognitionActive && !muted;
  assistantSpeaking = true;
  if (resumeRecognition) stopRecognition();
  orb.classList.add("speaking");
  orb.classList.remove("listening");
  micState.textContent = "🔊 বলছি...";

  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language, slow }),
    });
    if (!res.ok) throw new Error(`TTS request failed: ${res.status}`);
    const audioUrl = URL.createObjectURL(await res.blob());
    stopAudio();
    currentAudio = new Audio(audioUrl);
    await currentAudio.play();
    await new Promise((resolve) => {
      const finish = () => {
        URL.revokeObjectURL(audioUrl);
        if (currentAudio && currentAudio.src === audioUrl) currentAudio = null;
        orb.classList.remove("speaking");
        micState.textContent = muted ? "🔇 মাইক বন্ধ" : "🎙️ শুনছি...";
        assistantSpeaking = false;
        ignoreSpeechUntil = Date.now() + 500;
        if (resumeRecognition && !muted) startRecognition();
        resolve();
      };
      currentAudio.onended = finish;
      currentAudio.onerror = finish;
    });
  } catch (err) {
    console.warn("Bangla TTS unavailable:", err);
    orb.classList.remove("speaking");
    micState.textContent = muted ? "🔇 মাইক বন্ধ" : "🎙️ শুনছি...";
    assistantSpeaking = false;
    ignoreSpeechUntil = Date.now() + 500;
    if (resumeRecognition && !muted) startRecognition();
  }
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
    meta = `<span class="confidence-badge">${category.replaceAll("_", " ")} ${pct}%</span>`;
  }
  div.innerHTML = `<b>${label}${meta}</b>${escapeHtml(text)}`;
  transcriptBox.appendChild(div);
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

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
