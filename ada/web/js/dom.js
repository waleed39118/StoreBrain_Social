// Tiny DOM builder. All text goes through textContent — never innerHTML — so data from the
// server or user input can never inject markup/scripts (XSS-safe by construction).
export function h(tag, attrs = {}, ...children) {
  const el = document.createElementNS(
    tag === 'svg' || attrs._svg ? 'http://www.w3.org/2000/svg' : 'http://www.w3.org/1999/xhtml', tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false || k === '_svg') continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.setAttribute('class', v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'value' || k === 'checked' || k === 'selected' || k === 'hidden' || k === 'disabled') el[k] = v;
    else if (k in el && !(el instanceof SVGElement) && typeof v !== 'string') el[k] = v;
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  append(el, children);
  return el;
}

export function svg(tag, attrs = {}, ...children) { return h(tag, { ...attrs, _svg: true }, ...children); }

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function clear(el) { while (el.firstChild) el.firstChild.remove(); return el; }
export function mount(el, ...children) { clear(el); append(el, children); return el; }

let toastTimer;
export function toast(msg, kind = 'info') {
  const box = document.getElementById('toast');
  mount(box, h('div', { class: `toast toast-${kind}`, role: kind === 'error' ? 'alert' : 'status' }, msg));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => clear(box), 4000);
}

export function modal(title, body, actions = [], { onClose } = {}) {
  const root = document.getElementById('modal');
  let closed = false;
  const close = () => {
    if (closed) return; closed = true;
    clear(root); root.hidden = true; document.removeEventListener('keydown', esc); onClose?.();
  };
  const esc = (e) => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', esc);
  const dlg = h('div', { class: 'modal-card', role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
    h('div', { class: 'modal-head' }, h('h2', {}, title),
      h('button', { class: 'icon-btn', 'aria-label': '×', onclick: close }, '×')),
    h('div', { class: 'modal-body' }, body),
    actions.length ? h('div', { class: 'modal-actions' }, actions) : null);
  mount(root, h('div', { class: 'modal-backdrop', onclick: (e) => { if (e.target === e.currentTarget) close(); } }, dlg));
  root.hidden = false;
  dlg.querySelector('input,select,textarea,button.primary')?.focus();
  return close;
}

export function fmtMoney(v, currency) {
  const lang = document.documentElement.lang || 'ar';
  try {
    return new Intl.NumberFormat(lang === 'ar' ? 'ar-SA-u-nu-latn' : 'en-US',
      { style: 'currency', currency: currency || 'SAR' }).format(Number(v));
  } catch { return `${Number(v).toFixed(2)} ${currency || ''}`; }
}

export function fmtDate(iso) {
  const lang = document.documentElement.lang || 'ar';
  return new Intl.DateTimeFormat(lang === 'ar' ? 'ar-SA-u-nu-latn-ca-gregory' : 'en-GB',
    { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
}

export function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = h('a', { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export function uuid() {
  return crypto.randomUUID ? crypto.randomUUID()
    : ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, c =>
      (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
}

export const modalOpen = () => !document.getElementById('modal').hidden;
