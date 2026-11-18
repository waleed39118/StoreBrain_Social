// Sign-in: owner via SMS code to the registered number; staff via phone + PIN.
// Also hosts first-run setup (pair the SMS phone with the installer's setup code).
import { api, session } from '../api.js';
import { h, mount, toast, modal } from '../dom.js';
import { t, setLang, getLang } from '../i18n.js';
import { qrCanvas } from '../qr.js';

export async function render(root, onLoggedIn) {
  let tab = 'owner', step = 'phone', phone = '', timer = null, wait = 0;
  let setup = { setup_available: false };
  try { setup = await api('/setup/state'); } catch { /* offline */ }
  const device = `${navigator.platform || 'device'} ${/Mobi|Android|iPad|iPhone/.test(navigator.userAgent) ? 'mobile' : 'desktop'}`;

  const done = async (res) => { session.save(res.token, res.user); clearInterval(timer); await onLoggedIn(); };
  const fail = (e) => toast(e.status === 0 ? t('offline_action') : t('error_generic', { m: e.message }), 'error');

  function draw() {
    const form = h('form', { class: 'stack', onsubmit: submit, autocomplete: 'on' });
    if (tab === 'owner' && step === 'phone') {
      form.append(field(t('phone'), h('input', { name: 'phone', type: 'tel', inputmode: 'tel', autocomplete: 'tel', required: true, value: phone, dir: 'ltr', placeholder: '05xxxxxxxx' })),
        h('button', { class: 'primary big', type: 'submit' }, t('send_code')));
    } else if (tab === 'owner') {
      form.append(h('p', { class: 'muted' }, t('code_sent')),
        field(t('code'), h('input', { name: 'code', inputmode: 'numeric', autocomplete: 'one-time-code', pattern: '\\d{6}', maxlength: 6, required: true, dir: 'ltr', class: 'otp' })),
        h('button', { class: 'primary big', type: 'submit' }, t('verify')),
        h('div', { class: 'row between' },
          h('button', { type: 'button', class: 'link', onclick: () => { step = 'phone'; draw(); } }, t('change_number')),
          h('button', { type: 'button', class: 'link', disabled: wait > 0, onclick: () => requestCode() }, wait > 0 ? t('resend_in', { s: wait }) : t('resend'))));
    } else {
      form.append(field(t('phone'), h('input', { name: 'phone', type: 'tel', inputmode: 'tel', required: true, dir: 'ltr' })),
        field(t('pin'), h('input', { name: 'pin', type: 'password', inputmode: 'numeric', pattern: '\\d{4,8}', maxlength: 8, required: true, dir: 'ltr', autocomplete: 'current-password' })),
        h('button', { class: 'primary big', type: 'submit' }, t('verify')));
    }
    mount(root, h('div', { class: 'login' },
      h('div', { class: 'login-card card' },
        h('div', { class: 'login-brand' }, h('img', { src: '/icons/icon-192.png', alt: '', width: 72, height: 72 }),
          h('h1', {}, t('app')), h('p', { class: 'muted' }, t('tagline'))),
        h('div', { class: 'tabs', role: 'tablist' },
          tabBtn('owner', t('owner_tab')), tabBtn('staff', t('staff_tab'))),
        form,
        h('div', { class: 'row between login-foot' },
          h('button', { class: 'link', onclick: () => { setLang(getLang() === 'ar' ? 'en' : 'ar'); draw(); } }, getLang() === 'ar' ? 'English' : 'العربية'),
          setup.setup_available ? h('button', { class: 'link', onclick: firstSetup }, t('first_setup')) : null))));
    form.querySelector('input')?.focus();
  }

  const tabBtn = (key, label) => h('button', { role: 'tab', 'aria-selected': String(tab === key), class: tab === key ? 'tab active' : 'tab',
    onclick: () => { tab = key; step = 'phone'; draw(); } }, label);

  async function requestCode() {
    try {
      await api('/auth/otp/request', { method: 'POST', body: { phone } });
      step = 'code'; wait = 60; clearInterval(timer);
      timer = setInterval(() => { wait -= 1; if (wait <= 0) clearInterval(timer); if (step === 'code') { const b = root.querySelectorAll('.link')[1]; if (b) { b.disabled = wait > 0; b.textContent = wait > 0 ? t('resend_in', { s: wait }) : t('resend'); } } }, 1000);
      draw();
    } catch (e) { fail(e); }
  }

  async function submit(e) {
    e.preventDefault();
    const f = new FormData(e.target);
    const btn = e.target.querySelector('button[type=submit]'); btn.disabled = true;
    try {
      if (tab === 'owner' && step === 'phone') { phone = f.get('phone'); await requestCode(); }
      else if (tab === 'owner') await done(await api('/auth/otp/verify', { method: 'POST', body: { phone, code: f.get('code'), device_name: device } }));
      else await done(await api('/auth/pin/login', { method: 'POST', body: { phone: f.get('phone'), pin: f.get('pin'), device_name: device } }));
    } catch (err) { fail(err); } finally { btn.disabled = false; }
  }

  function firstSetup() {
    const input = h('input', { required: true, dir: 'ltr', autocomplete: 'off', minlength: 8 });
    const out = h('div', { class: 'stack' });
    const close = modal(t('first_setup'), h('form', { class: 'stack', onsubmit: async (e) => {
      e.preventDefault();
      try {
        const pair = await api('/setup/pairing', { method: 'POST', body: { setup_code: input.value } });
        mount(out, h('p', {}, t('pairing_help')), h('div', { class: 'qr-wrap' }, qrCanvas(pair.qr)),
          h('button', { type: 'button', onclick: async () => { await navigator.clipboard.writeText(pair.qr); toast(t('copied')); } }, t('copy')));
      } catch (err) { fail(err); }
    } }, field(t('setup_code'), input), h('button', { class: 'primary', type: 'submit' }, t('show_pairing')), out));
    void close;
  }

  draw();
}

export function field(label, input) {
  return h('label', { class: 'field' }, h('span', {}, label), input);
}
