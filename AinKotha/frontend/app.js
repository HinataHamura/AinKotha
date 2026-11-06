// AinKotha frontend — voice call UI wired to /api/chat (FR-1, FR-2, FR-8)
const API_URL = "/api/chat";
const SESSION_ID = crypto.randomUUID();
const SILENCE_TIMEOUT_MS = 60000; // FR-1.5

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
let muted = false;
let silenceTimer = null;
let callLog = []; // {category, laws, services} accumulated for summary
let usingTextMode = false;
let currentAudio = null;
let language = "bn";

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
  emergencyBanner.classList.add("hidden");

  greet();

  if (textMode || !setupRecognition()) {
    textFallback.classList.remove("hidden");
    micState.textContent = "⌨️ টেক্সটে লিখুন";
  } else {
    textFallback.classList.add("hidden");
    startRecognition();
  }
  resetSilenceTimer();
}

function greet() {
  const text = language === "en"
    ? "Hello. I can share general information about laws and helplines in Bangladesh. I am not a lawyer. Please tell me your problem."
    : "নমস্কার। আমি AinKotha, আইনি তথ্য ও হেল্পলাইন সম্পর্কে সাধারণ তথ্য দিতে পারি। আমি একজন আইনজীবী নই। আপনার সমস্যা বলুন।";
  addBubble("bot", text);
  speak(text);
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
    if (recognitionActive && !muted) {
      try { recognition.start(); } catch (e) {}
    }
  };
  return true;
}

function startRecognition() {
  if (!recognition) return;
  recognitionActive = true;
  try { recognition.start(); } catch (e) {}
  orb.classList.add("listening");
  callStatus.textContent = "সংযোগ হয়েছে — কথা বলুন";
  micState.textContent = "🎙️ শুনছি...";
}

function stopRecognition() {
  recognitionActive = false;
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

async function speak(text) {
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language }),
    });
    if (!res.ok) throw new Error(`TTS request failed: ${res.status}`);
    const audioUrl = URL.createObjectURL(await res.blob());
    stopAudio();
    currentAudio = new Audio(audioUrl);
    currentAudio.onended = () => {
      URL.revokeObjectURL(audioUrl);
      currentAudio = null;
    };
    await currentAudio.play();
  } catch (err) {
    console.warn("Bangla TTS unavailable:", err);
  }
}

// ---------- Transcript UI ----------
function addBubble(who, text) {
  const div = document.createElement("div");
  div.className = who;
  const label = who === "me" ? "আপনি" : "AinKotha";
  div.innerHTML = `<b>${label}</b>${escapeHtml(text)}`;
  transcriptBox.appendChild(div);
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- Backend call ----------
async function handleUserTranscript(text) {
  addBubble("me", text);
  callStatus.textContent = "ভাবছি...";
  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: SESSION_ID, transcript: text, language }),
    });
    const data = await res.json();
    addBubble("bot", data.reply_text);
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
      row.innerHTML = `<span>${s.name_bn}</span><a href="tel:${s.phone_number}">${s.phone_number}</a>`;
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
  consentScreen.classList.remove("hidden");
});

$("helpBtn").addEventListener("click", () => {
  const text = language === "en"
    ? "Emergency service 999. Violence against women and children helpline 109. National legal aid 16430. Child helpline 1098."
    : "জরুরি সেবা ৯৯৯। নারী ও শিশু নির্যাতন হেল্পলাইন ১০৯। জাতীয় আইনগত সহায়তা ১৬৪৩০। চাইল্ড হেল্পলাইন ১০৯৮।";
  addBubble("bot", text);
  speak(text);
});

$("languageBtn").addEventListener("click", () => {
  language = language === "bn" ? "en" : "bn";
  $("languageBtn").textContent = language === "bn" ? "English" : "বাংলা";
});
