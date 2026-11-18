// Verifies: service worker installs; the app reloads with NO network (offline shell);
// vendored ZXing loads under the strict CSP and exposes the camera reader API.
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const { chromium } = createRequire(import.meta.url)('playwright');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';

const browser = await chromium.launch();
const ctx = await browser.newContext();
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error' && /Content Security Policy/.test(m.text())) errors.push(m.text()); });

await page.goto(BASE);
await page.waitForSelector('.login-card');
await page.evaluate(async () => { await navigator.serviceWorker.ready; });
await page.waitForTimeout(500);
await page.reload();                                   // now controlled by the SW
await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
await page.waitForTimeout(1000);                       // let the shell finish caching

await ctx.setOffline(true);
await page.reload();
await page.waitForSelector('.login-card', { timeout: 10000 });
console.log('offline reload OK');

const zx = await page.evaluate(() => new Promise((resolve) => {
  const s = document.createElement('script'); s.src = '/vendor/zxing-0.23.0.min.js';
  s.onload = () => { const r = new window.ZXing.BrowserMultiFormatReader(); resolve(typeof r.decodeFromStream + '/' + typeof r.reset); };
  s.onerror = () => resolve('load-failed'); document.head.append(s);
}));
assert.equal(zx, 'function/function', `zxing api: ${zx}`);
assert.deepEqual(errors, []);
await browser.close();
console.log('OFFLINE+CSP OK');
