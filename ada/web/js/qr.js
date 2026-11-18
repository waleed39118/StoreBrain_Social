// QR rendering with the vendored qrcode-generator (MIT). Drawn on a canvas, no network.
import qrcode from '/vendor/qrcode-generator-2.0.4.mjs';
import { h } from './dom.js';

export function qrCanvas(text, size = 260) {
  const qr = qrcode(0, 'M');
  qr.addData(text, 'Byte');
  qr.make();
  const n = qr.getModuleCount(), quiet = 4, scale = Math.floor(size / (n + quiet * 2)) || 2;
  const px = (n + quiet * 2) * scale;
  const c = h('canvas', { width: px, height: px, class: 'qr', role: 'img', 'aria-label': 'QR' });
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, px, px); ctx.fillStyle = '#000';
  for (let r = 0; r < n; r++) for (let col = 0; col < n; col++)
    if (qr.isDark(r, col)) ctx.fillRect((col + quiet) * scale, (r + quiet) * scale, scale, scale);
  return c;
}
