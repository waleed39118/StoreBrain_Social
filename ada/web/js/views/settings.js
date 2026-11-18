// Settings: store profile (owner), SMS phone pairing/status, local AI, backups, devices, language.
import { api, session } from '../api.js';
import { h, mount, toast, downloadBlob, fmtDate } from '../dom.js';
import { t, setLang, getLang } from '../i18n.js';
import { qrCanvas } from '../qr.js';
import { field } from './login.js';
import { sessionsCard } from './staff.js';
import { wipe } from '../db.js';

const TIMEZONES = ['Asia/Riyadh', 'Asia/Dubai', 'Asia/Kuwait', 'Asia/Qatar', 'Asia/Bahrain', 'Asia/Muscat', 'Africa/Cairo',
  'Asia/Amman', 'Asia/Baghdad', 'Asia/Beirut', 'Africa/Casablanca', 'Africa/Tunis', 'Africa/Algiers', 'Europe/London', 'UTC'];
const CURRENCIES = ['SAR', 'AED', 'KWD', 'QAR', 'BHD', 'OMR', 'EGP', 'JOD', 'IQD', 'MAD', 'TND', 'USD', 'EUR'];

export async function render(root, state) {
  const owner = state.user.role === 'owner';
  const cards = [langCard()];
  if (owner) cards.unshift(await profileCard(state), await gatewayCard(), await aiCard(), await backupsCard());
  cards.push(await sessionsCard(), h('div', { class: 'card row gap wrap' },
    h('button', { onclick: async () => { try { await api('/auth/logout', { method: 'POST' }); } catch { /* ignore */ } session.clear(); await wipe(); location.hash = ''; location.reload(); } }, t('logout')),
    h('button', { class: 'ghost', onclick: async () => { await api('/auth/logout-all', { method: 'POST' }); session.clear(); await wipe(); location.reload(); } }, t('logout_all'))));
  mount(root, h('div', { class: 'stack settings' }, cards));
}

function langCard() {
  return h('div', { class: 'card row between' }, h('h2', {}, t('language')),
    h('div', { class: 'seg' }, [['ar', 'العربية'], ['en', 'English']].map(([k, l]) =>
      h('button', { class: getLang() === k ? 'active' : '', onclick: () => { setLang(k); location.reload(); } }, l))));
}

async function profileCard(state) {
  const p = await api('/store/profile');
  const inp = (name, attrs = {}) => h('input', { name, value: p[name] ?? '', ...attrs });
  const sel = (name, opts) => h('select', { name }, opts.map(o => h('option', { value: o, selected: p[name] === o }, o)));
  const f = h('form', { class: 'form-grid', onsubmit: async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f).entries());
    const body = { ...p, ...d, tax_rate: Number(d.tax_rate), prices_include_tax: f.elements.prices_include_tax.checked, setup_completed: true };
    try { state.profile = await api('/store/profile', { method: 'PUT', body }); localStorage.setItem('ada.profile', JSON.stringify(state.profile)); toast(t('saved'), 'ok'); }
    catch (err) { toast(t('error_generic', { m: err.message }), 'error'); }
  } },
    field(t('store_name'), inp('store_name', { required: true })), field(t('store_phone'), inp('store_phone', { dir: 'ltr' })),
    field(t('address'), inp('address')), field(t('tax_number'), inp('tax_number', { dir: 'ltr' })),
    field(t('currency'), sel('currency', CURRENCIES)), field(t('tax_rate'), inp('tax_rate', { type: 'number', step: '0.01', min: 0, max: 100, dir: 'ltr' })),
    field(t('timezone'), sel('timezone', TIMEZONES.includes(p.timezone) ? TIMEZONES : [p.timezone, ...TIMEZONES])),
    field(t('language'), h('select', { name: 'language' }, [['ar', 'العربية'], ['en', 'English']].map(([v, l]) => h('option', { value: v, selected: p.language === v }, l)))),
    field(t('receipt_footer'), inp('receipt_footer')),
    h('label', { class: 'row gap' }, h('input', { type: 'checkbox', name: 'prices_include_tax', checked: p.prices_include_tax }), t('prices_include_tax')),
    h('div', { class: 'form-actions' }, h('button', { class: 'primary', type: 'submit' }, t('save'))));
  return h('div', { class: 'card' }, h('h2', {}, t('store_profile')), f);
}

async function gatewayCard() {
  const card = h('div', { class: 'card' });
  async function load() {
    try {
      const st = await api('/system/sms-gateway/status');
      const qrBox = h('div', { class: 'qr-wrap', hidden: true });
      mount(card, h('div', { class: 'row between' }, h('h2', {}, t('sms_phone')),
          h('span', { class: `pill ${st.online ? 'ok' : 'warn'}` }, st.online ? t('gw_online') : t('gw_offline'))),
        h('p', { class: 'muted' }, st.device || '—', st.last_seen ? ` • ${t('last_seen')}: ${fmtDate(st.last_seen)}` : ''),
        h('p', { class: 'muted' }, Object.entries(st.last_24h).map(([k, v]) => `${k}: ${v}`).join(' • ') || '—'),
        h('div', { class: 'row gap wrap' },
          h('button', { onclick: async () => {
            const pair = await api('/system/sms-gateway/pairing');
            mount(qrBox, h('p', {}, t('pairing_help')), qrCanvas(pair.qr),
              h('button', { onclick: async () => { await navigator.clipboard.writeText(pair.qr); toast(t('copied')); } }, t('copy')));
            qrBox.hidden = !qrBox.hidden;
          } }, t('show_pairing')),
          h('button', { onclick: async () => { await api('/system/sms-gateway/test', { method: 'POST' }); toast(t('test_sms_sent'), 'ok'); } }, t('send_test_sms'))),
        qrBox);
    } catch (e) { mount(card, h('h2', {}, t('sms_phone')), h('p', { class: 'muted' }, e.message)); }
  }
  await load();
  return card;
}

async function aiCard() {
  let st = { enabled: false };
  try { st = await api('/system/ai'); } catch { /* ignore */ }
  const label = !st.enabled ? t('ai_off') : st.reachable ? `${t('ai_on')} — ${st.model}` : t('ai_unreachable');
  return h('div', { class: 'card row between' }, h('h2', {}, t('local_ai')), h('span', { class: `pill ${st.enabled && st.reachable ? 'ok' : 'warn'}` }, label));
}

async function backupsCard() {
  const card = h('div', { class: 'card' });
  async function load() {
    const rows = await api('/system/backups').catch(() => []);
    mount(card, h('div', { class: 'row between' }, h('h2', {}, t('backups')),
        h('button', { onclick: async () => { await api('/system/backups', { method: 'POST' }); toast(t('saved'), 'ok'); load(); } }, t('backup_now'))),
      h('ul', { class: 'plain' }, rows.slice(0, 7).map(b => h('li', { class: 'row between' },
        h('span', {}, `${fmtDate(b.created_at)} • ${(b.size / 1024).toFixed(0)} KB`),
        h('button', { class: 'small', onclick: async () => downloadBlob(await (await api(`/system/backups/${b.name}`, { raw: true })).blob(), b.name) }, t('download'))))));
  }
  await load();
  return card;
}
