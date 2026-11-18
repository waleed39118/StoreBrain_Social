// Render still frames at given times for design review: node stills.js out_dir t1 t2 ...
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [out, ...times] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await p.goto('file://' + path.join(__dirname, 'promo.html'));
  await p.evaluate(() => document.fonts.ready);
  for (const t of times) {
    await p.evaluate((x) => window.render(x), parseFloat(t));
    await p.screenshot({ path: path.join(out, `t${t}.png`) });
  }
  await b.close();
})();
