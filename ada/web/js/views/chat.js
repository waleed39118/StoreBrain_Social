// Conversational Ada: text or voice (Whisper on the server); replies read aloud locally.
import { api } from '../api.js';
import { h, mount, toast } from '../dom.js';
import { t, getLang } from '../i18n.js';

const history = [];   // kept for the session only

export async function render(root) {
  let speak = localStorage.getItem('ada.speak') !== '0';
  let recorder = null, chunks = [];
  const list = h('div', { class: 'chat-list', role: 'log', 'aria-live': 'polite' });
  const input = h('input', { class: 'grow', placeholder: t('chat_placeholder'), 'aria-label': t('chat_placeholder'), maxlength: 1000 });
  const mic = h('button', { class: 'icon-btn big mic', 'aria-label': t('hold_to_talk'), title: t('hold_to_talk'), onclick: toggleRec }, '🎙️');

  if (!history.length) history.push({ who: 'ada', text: t('chat_hello') });

  function draw() {
    mount(list, history.map(m => h('div', { class: `bubble ${m.who}` },
      m.transcript ? h('small', { class: 'muted' }, `🎙️ ${m.transcript}`) : null, h('div', {}, m.text),
      m.confirm && !m.done ? h('div', { class: 'row gap confirm-row' },
        h('button', { class: 'primary small', onclick: () => { m.done = true; ask(m.confirm, true); } }, t('yes')),
        h('button', { class: 'small', onclick: () => { m.done = true; draw(); } }, t('no'))) : null)));
    list.scrollTop = list.scrollHeight;
  }

  function say(text, lang) {
    if (!speak || !('speechSynthesis' in window)) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === 'ar' ? 'ar-SA' : 'en-US';
    const v = speechSynthesis.getVoices().find(v => v.lang?.toLowerCase().startsWith(u.lang.slice(0, 2)));
    if (v) u.voice = v;
    speechSynthesis.speak(u);
  }

  async function ask(text, confirmed = false) {
    if (!text.trim()) return;
    history.push({ who: 'me', text: confirmed ? `✓ ${t('confirm')}` : text }); draw();
    try {
      const r = await api('/ada/chat', { method: 'POST', body: { text, language: getLang() } });
      history.push({ who: 'ada', text: r.reply, confirm: r.data?.confirm }); draw(); say(r.reply, r.language);
    } catch (e) {
      history.push({ who: 'ada', text: e.status === 0 ? t('offline_action') : t('error_generic', { m: e.message }) }); draw();
    }
  }

  async function toggleRec() {
    if (recorder) { recorder.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find(x => window.MediaRecorder?.isTypeSupported?.(x)) || '';
      recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      chunks = [];
      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach(tr => tr.stop());
        mic.classList.remove('rec'); mic.textContent = '🎙️';
        const blob = new Blob(chunks, { type: recorder.mimeType });
        recorder = null;
        const fd = new FormData();
        fd.append('audio', blob, blob.type.includes('mp4') ? 'voice.m4a' : 'voice.webm');
        fd.append('speak', 'false');
        try {
          const r = await api('/ada/voice', { method: 'POST', form: fd });
          history.push({ who: 'me', text: r.transcript, transcript: null }, { who: 'ada', text: r.reply, confirm: r.data?.confirm });
          draw(); say(r.reply, r.language);
        } catch { toast(t('voice_failed'), 'error'); }
      };
      recorder.start();
      mic.classList.add('rec'); mic.textContent = '⏹';
      toast(t('listening'));
      setTimeout(() => recorder?.state === 'recording' && recorder.stop(), 20_000);
    } catch { toast(t('mic_denied'), 'error'); }
  }

  mount(root, h('div', { class: 'chat card' }, list,
    h('form', { class: 'chat-input row gap', onsubmit: (e) => { e.preventDefault(); const v = input.value; input.value = ''; ask(v); } },
      mic, input, h('button', { class: 'primary', type: 'submit' }, t('send'))),
    h('label', { class: 'row gap small' }, h('input', { type: 'checkbox', checked: speak,
      onchange: (e) => { speak = e.target.checked; localStorage.setItem('ada.speak', speak ? '1' : '0'); } }), t('speak_replies'))));
  draw(); input.focus();
  return { destroy: () => { recorder?.stop(); speechSynthesis?.cancel?.(); } };
}
