const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ args: ['--ignore-certificate-errors'] });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });

  // 1. Task pane outside a Word host
  const page1 = await context.newPage();
  const errors1 = [];
  page1.on('console', (msg) => { if (msg.type() === 'error') errors1.push(msg.text()); });
  page1.on('pageerror', (err) => errors1.push('pageerror: ' + err.message));
  await page1.goto('https://localhost:3000/taskpane.html', { waitUntil: 'networkidle', timeout: 20000 }).catch((e) => errors1.push('nav error: ' + e.message));
  await page1.waitForTimeout(3000);
  await page1.screenshot({ path: 'scratch/screenshot_taskpane.png', fullPage: true });
  console.log('--- taskpane.html body text (first 500 chars) ---');
  console.log((await page1.textContent('body').catch(() => '')).slice(0, 500));
  console.log('--- taskpane.html console errors ---');
  console.log(JSON.stringify(errors1, null, 2));

  await browser.close();
})();
