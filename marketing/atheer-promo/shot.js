// Screenshot the real Atheer /docs page; Swagger UI assets are served from the local npm copy.
const { chromium } = require('playwright');
const path = require('path');
const dist = path.join(__dirname, 'node_modules', 'swagger-ui-dist');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await p.route(/cdn\.jsdelivr\.net/, (route) => {
    const file = path.basename(new URL(route.request().url()).pathname);
    route.fulfill({ path: path.join(dist, file) });
  });
  await p.route(/fastapi\.tiangolo\.com/, (route) => route.fulfill({ status: 204, body: '' }));
  await p.goto('http://localhost:8777/docs', { waitUntil: 'networkidle' });
  await p.waitForSelector('.opblock', { timeout: 15000 });
  await p.waitForTimeout(500);
  await p.screenshot({ path: process.argv[2] });
  await b.close();
})();
