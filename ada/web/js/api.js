// API client: bearer token, JSON/form bodies, consistent errors, auto-logout on 401.
const TOKEN_KEY = 'ada.token';
const USER_KEY = 'ada.user';

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export const session = {
  get token() { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  get user() { try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch { return null; } },
  save(token, user) { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USER_KEY, JSON.stringify(user)); },
  clear() { try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); } catch { /* ignore */ } },
};

export async function api(path, { method = 'GET', body, form, raw = false, headers = {}, signal } = {}) {
  const opts = { method, headers: { Accept: 'application/json', ...headers }, signal, cache: 'no-store' };
  if (session.token) opts.headers.Authorization = `Bearer ${session.token}`;
  if (form) opts.body = form;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json'; }
  let res;
  try { res = await fetch(`/api/v1${path}`, opts); }
  catch { throw new ApiError(0, 'offline'); }
  if (res.status === 401 && session.token && !path.startsWith('/auth/')) {
    session.clear();
    window.dispatchEvent(new Event('ada:logout'));
  }
  if (raw) { if (!res.ok && res.status !== 304) throw new ApiError(res.status, await errText(res)); return res; }
  if (res.status === 204) return null;
  if (!res.ok) throw new ApiError(res.status, await errText(res));
  return res.json();
}

async function errText(res) {
  try {
    const j = await res.json();
    if (typeof j.detail === 'string') return j.detail;
    if (Array.isArray(j.detail)) return j.detail.map(d => d.msg).join('; ');
  } catch { /* ignore */ }
  return `HTTP ${res.status}`;
}
