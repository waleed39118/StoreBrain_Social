// Barcode input: (1) USB/Bluetooth scanners that type like a keyboard ("wedge"), detected by
// fast keystrokes ending in Enter; (2) camera scanning via the native BarcodeDetector or the
// bundled ZXing library (iPad/Safari). No network services involved.
import { h, modal } from './dom.js';
import { t } from './i18n.js';

export function onWedgeScan(callback) {
  let buf = '', last = 0;
  const handler = (e) => {
    const now = performance.now();
    if (now - last > 60) buf = '';
    last = now;
    if (e.key === 'Enter') {
      if (buf.length >= 6) {
        e.preventDefault();
        e.stopPropagation();          // the scan must not also trigger the focused input's Enter
        const code = buf; buf = '';
        const tgt = e.target;
        if (tgt && tgt.tagName === 'INPUT' && tgt.value.endsWith(code)) tgt.value = tgt.value.slice(0, -code.length);
        callback(code);
      }
      buf = '';
    } else if (e.key.length === 1) buf += e.key;
  };
  document.addEventListener('keydown', handler, true);
  return () => document.removeEventListener('keydown', handler, true);
}

let zxingLoaded;
function loadZxing() {
  zxingLoaded ??= new Promise((resolve, reject) => {
    const s = h('script', { src: '/vendor/zxing-0.23.0.min.js' });
    s.onload = () => resolve(window.ZXing); s.onerror = reject;
    document.head.append(s);
  });
  return zxingLoaded;
}

/** Opens a camera dialog; resolves with the scanned text (or null if closed). */
export function cameraScan({ qr = false } = {}) {
  return new Promise(async (resolve) => {
    const video = h('video', { class: 'scan-video', playsinline: true, muted: true, autoplay: true });
    let stream, stopped = false, zxReader;
    const stop = () => {
      stopped = true;
      stream?.getTracks().forEach(tr => tr.stop());
      try { zxReader?.reset(); } catch { /* ignore */ }
    };
    const close = modal(t('scan_title'), h('div', { class: 'scan-box' }, video, h('div', { class: 'scan-frame' }),
      h('p', { class: 'muted' }, t('scan_hint'))));
    const observer = new MutationObserver(() => {
      if (!document.body.contains(video)) { observer.disconnect(); if (!stopped) { stop(); resolve(null); } }
    });
    observer.observe(document.getElementById('modal'), { childList: true, subtree: true });
    const done = (text) => { if (stopped) return; stop(); observer.disconnect(); close(); resolve(text); };
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      video.srcObject = stream;
      await video.play();
      if ('BarcodeDetector' in window) {
        const formats = qr ? ['qr_code'] : ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf', 'qr_code'];
        const det = new window.BarcodeDetector({ formats });
        const loop = async () => {
          if (stopped) return;
          try { const r = await det.detect(video); if (r.length) return done(r[0].rawValue); } catch { /* frame */ }
          requestAnimationFrame(loop);
        };
        loop();
      } else {
        const ZX = await loadZxing();
        zxReader = new ZX.BrowserMultiFormatReader();
        zxReader.decodeFromStream(stream, video, (result) => { if (result) done(result.getText()); });
      }
    } catch {
      stop(); observer.disconnect(); close();
      resolve(null);
      const { toast } = await import('./dom.js');
      toast(t('camera_denied'), 'error');
    }
  });
}
