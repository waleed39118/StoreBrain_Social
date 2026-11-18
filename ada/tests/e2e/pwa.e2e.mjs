// End-to-end test of the Ada PWA in Chromium: login via SMS OTP (gateway API), onboarding,
// POS with keyboard-wedge barcode scan, offline sale + auto-sync, chat, dashboard, settings.
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');
import assert from 'node:assert/strict';

const BASE = process.env.BASE || 'http://127.0.0.1:8765';
const GW = { 'X-Gateway-Token': 'gateway-token-gateway-token-gateway-token' };
const shots = process.env.SHOTS;

async function otp() {
  for (let i = 0; i < 20; i++) {
    const r = await fetch(`${BASE}/api/v1/sms-gateway/claim?wait=2`, { method: 'POST', headers: GW });
    const msgs = await r.json();
    if (msgs.length) {
      await fetch(`${BASE}/api/v1/sms-gateway/${msgs[0].id}/ack`, { method: 'POST', headers: { ...GW, 'Content-Type': 'application/json' }, body: '{"ok":true}' });
      return msgs[0].body.match(/\b(\d{6})\b/)[1];
    }
  }
  throw new Error('no OTP');
}

process.on('unhandledRejection', async (e) => {
  console.error(e); console.error('console errors:', errors);
  try { await page.screenshot({ path: `${shots || '.'}/FAILED.png` }); } catch { /* ignore */ }
  process.exit(1);
});
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 820 }, locale: 'ar-SA', serviceWorkers: 'block' });
const page = await ctx.newPage();
const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('response', (r) => { if (r.status() >= 400) errors.push(`HTTP ${r.status()} ${r.url()}`); });
page.on('pageerror', (e) => errors.push(String(e)));
const shot = async (n) => shots && page.screenshot({ path: `${shots}/${n}.png` });

// 1. Login (Arabic, RTL)
await page.goto(BASE);
await page.waitForSelector('.login-card');
assert.equal(await page.getAttribute('html', 'dir'), 'rtl');
await shot('01-login');
await page.fill('input[name=phone]', '0551234567');
await page.click('button[type=submit]');
await page.waitForSelector('input[name=code]');
await page.fill('input[name=code]', await otp());
await page.click('button[type=submit]');

// 2. Onboarding with demo catalog
await page.waitForSelector('.modal-card');
await page.fill('.modal-card input:not([type=checkbox])', 'بقالة النور');
await page.click('.modal-card button[type=submit]');
await page.waitForSelector('.tile');
assert.ok((await page.locator('.tile').count()) >= 16, 'demo products shown');
assert.match(await page.textContent('.brand strong'), /بقالة النور/);
await shot('02-pos');

// 3. Keyboard-wedge barcode scan (EAN of demo item #1 = Fresh Milk) + checkout
await page.focus('.search');
await page.keyboard.type('2000000000015', { delay: 5 });
await page.keyboard.press('Enter');
await page.waitForSelector('.cart-line');
assert.equal(await page.inputValue('.search'), '', 'scanned code stripped from search box');
await page.locator('.tile').filter({ hasText: 'بيض' }).first().click();
assert.equal(await page.locator('.cart-line').count(), 2);
await page.click('.cart-foot button.primary');
await page.waitForSelector('.receipt');
const receipt = await page.textContent('.receipt');

assert.match(receipt, /ضريبة/); assert.match(receipt, /حليب طازج/);
await shot('03-receipt');
await page.keyboard.press('Escape');

// 4. Offline sale -> queued -> auto-sync when back online
await ctx.setOffline(true);
await page.evaluate(() => window.dispatchEvent(new Event('offline')));
await page.locator('.tile').filter({ hasText: 'خبز' }).first().click();
await page.click('.cart-foot button.primary');
await page.waitForSelector('.toast-warn');
await page.waitForFunction(() => /1/.test(document.getElementById('net').textContent));
await shot('04-offline');
await ctx.setOffline(false);
await page.evaluate(() => window.dispatchEvent(new Event('online')));
await page.waitForFunction(() => !/:\s*1/.test(document.getElementById('net').textContent), null, { timeout: 15000 });

// 5. Sales history shows 2 sales (one synced from offline)
await page.goto(`${BASE}/#/sales`);
await page.waitForSelector('.table tbody tr');
assert.equal(await page.locator('.table tbody tr').count(), 2);

// 6. Chat with Ada
await page.goto(`${BASE}/#/chat`);
await page.fill('.chat-input input', 'كم باقي من حليب طازج 1 لتر');
await page.click('.chat-input button[type=submit]');
await page.waitForFunction(() => document.querySelectorAll('.bubble.ada').length >= 2);
const reply = await page.locator('.bubble.ada').last().textContent();
assert.match(reply, /39/, `stock reply: ${reply}`);
await shot('05-chat');

// 7. Dashboard + products + settings render
await page.goto(`${BASE}/#/dashboard`);
await page.waitForSelector('.kpi');
assert.equal(await page.locator('.bar').count(), 7);
await shot('06-dashboard');
await page.goto(`${BASE}/#/products`);
await page.waitForSelector('.table tbody tr');
await page.goto(`${BASE}/#/settings`);
await page.waitForSelector('text=هاتف الرسائل');
await page.click('text=عرض رمز ربط هاتف الرسائل');
await page.waitForSelector('canvas.qr');
await shot('07-settings');

// 8. English / LTR switch
await page.click('.topbar-actions button:has-text("EN")');
await page.waitForFunction(() => document.documentElement.dir === 'ltr');

// 9. Mobile layout (bottom nav)
await page.setViewportSize({ width: 390, height: 844 });
await page.goto(`${BASE}/#/pos`);
await page.waitForSelector('.tile');
await page.waitForTimeout(1500);
assert.equal(await page.locator('.view-slot .settings').count(), 0, 'stale settings view must not overwrite POS');
assert.ok(await page.locator('.tile').count() > 0);
await shot('08-mobile');

const real = errors.filter(e => !/Failed to load resource|net::ERR_INTERNET_DISCONNECTED/.test(e));
assert.deepEqual(real, [], `console errors: ${real.join('\n')}`);
await browser.close();
console.log('E2E OK');
