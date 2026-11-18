// First-login onboarding for the owner: store basics + optional demo catalog.
import { api } from '../api.js';
import { h, modal, toast } from '../dom.js';
import { t } from '../i18n.js';
import { field } from './login.js';
import { loadCatalog } from '../sync.js';

export function open(state) {
  const p = state.profile;
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || p.timezone;
  const name = h('input', { required: true, value: p.store_name });
  const demo = h('input', { type: 'checkbox', checked: true });
  const close = modal(t('first_setup'), h('form', { class: 'stack', onsubmit: async (e) => {
    e.preventDefault();
    try {
      const body = { ...p, store_name: name.value, timezone: tz, setup_completed: true };
      try { state.profile = await api('/store/profile', { method: 'PUT', body }); }
      catch { state.profile = await api('/store/profile', { method: 'PUT', body: { ...body, timezone: p.timezone } }); }
      if (demo.checked) { try { await api('/setup/demo-data', { method: 'POST' }); } catch { /* catalog not empty */ } }
      await loadCatalog({ force: true });
      localStorage.setItem('ada.profile', JSON.stringify(state.profile));
      close(); location.hash = '#/pos'; location.reload();
    } catch (err) { toast(t('error_generic', { m: err.message }), 'error'); }
  } }, h('p', {}, t('welcome_setup')), field(t('store_name'), name),
    h('label', { class: 'row gap' }, demo, t('load_demo')),
    h('button', { class: 'primary big', type: 'submit' }, t('finish_setup'))));
}
