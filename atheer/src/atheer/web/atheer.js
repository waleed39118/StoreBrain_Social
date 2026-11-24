// Atheer screens — shared helpers. No external libraries (works offline).
"use strict";

const Atheer = (() => {
  const KEY_STORE = "atheer.staffKey";

  function getKey() {
    try { return localStorage.getItem(KEY_STORE) || ""; } catch { return ""; }
  }
  function setKey(value) {
    try { value ? localStorage.setItem(KEY_STORE, value) : localStorage.removeItem(KEY_STORE); } catch { /* storage blocked */ }
  }

  const STATUS_MESSAGES = {
    401: "مفتاح الطاقم غير صحيح أو غير مُدخل.",
    402: "انتهى اشتراك أثير. تواصل مع المورّد لتجديده.",
    413: "الملف كبير جدًا.",
    429: "محاولات كثيرة خاطئة. انتظر قليلًا أو راجع الاستقبال.",
    503: "هذه الخدمة غير مفعّلة على الخادم.",
  };

  // JSON request to the Atheer API. Throws Error(message) with .status on failure.
  async function api(path, { method = "GET", body, staff = false } = {}) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (staff && getKey()) headers["X-API-Key"] = getKey();
    let res;
    try {
      res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch {
      const e = new Error("تعذّر الاتصال بخادم أثير. تأكد أنه يعمل.");
      e.status = 0;
      throw e;
    }
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
    if (!res.ok) {
      const msg = (data && data.message_ar) || STATUS_MESSAGES[res.status] ||
        (data && typeof data.detail === "string" ? data.detail : "حدث خطأ غير متوقع.");
      const e = new Error(msg);
      e.status = res.status;
      e.data = data;
      throw e;
    }
    return data;
  }

  // Safe element builder: text is always set with textContent (no HTML injection).
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  function toast(message, kind = "") {
    let host = document.getElementById("toast");
    if (!host) { host = el("div", { id: "toast", role: "status", "aria-live": "polite" }); document.body.append(host); }
    const item = el("div", { class: kind, text: message });
    host.replaceChildren(item);
    setTimeout(() => { if (item.isConnected) item.remove(); }, 4500);
  }

  // Times and dates are shown in the clinic's time zone (from /health), not the browser's.
  let clinicTz;
  function setTimeZone(tz) { clinicTz = tz || undefined; }
  function parts(date) {
    const fmt = new Intl.DateTimeFormat("en-GB", { timeZone: clinicTz, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    return Object.fromEntries(fmt.formatToParts(date).map((p) => [p.type, p.value]));
  }
  function hhmm(iso) {
    const p = parts(new Date(iso));
    return `${p.hour}:${p.minute}`;
  }
  function todayISO(offsetDays = 0) {
    const p = parts(new Date(Date.now() + offsetDays * 86400000));
    return `${p.year}-${p.month}-${p.day}`;
  }

  // "Room 2" -> "الغرفة 2"; mirrors the server's Arabic call-out wording.
  function counterAr(counter) {
    if (!counter) return "مكتب الاستقبال";
    const m = /^room\s*(\d+)$/i.exec(counter.trim());
    if (m) return `الغرفة ${m[1]}`;
    const places = { reception: "مكتب الاستقبال", pharmacy: "الصيدلية", lab: "المختبر", laboratory: "المختبر" };
    return places[counter.trim().toLowerCase()] || counter;
  }

  // Browser speech for screens without server-side speakers. Starts only after a user gesture.
  function speak(text, lang) {
    if (!("speechSynthesis" in window)) return false;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === "ar" ? "ar-SA" : "en-US";
    const voice = speechSynthesis.getVoices().find((v) => v.lang && v.lang.toLowerCase().startsWith(lang));
    if (voice) u.voice = voice;
    u.rate = 0.95;
    speechSynthesis.speak(u);
    return true;
  }

  function chime() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [660, 880].forEach((f, i) => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = f; o.type = "sine";
        g.gain.setValueAtTime(0.0001, ctx.currentTime + i * 0.25);
        g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + i * 0.25 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.25 + 0.45);
        o.connect(g).connect(ctx.destination);
        o.start(ctx.currentTime + i * 0.25); o.stop(ctx.currentTime + i * 0.25 + 0.5);
      });
    } catch { /* audio unavailable */ }
  }

  return { api, el, toast, hhmm, todayISO, counterAr, speak, chime, getKey, setKey, setTimeZone };
})();
