import { chromium, expect, test } from '@playwright/test';
import { fillQuizlet } from '../../extension/quizlet.js';
import path from 'node:path';

const payload = {
  title: 'Conservation vocabulary', tsv: 'conserve\tv. 節省；保護\nhabitat\tn. 棲息地',
  cardCount: 2, mode: 'auto', overwrite: false,
};

// A synthetic import form, not a captured or authenticated Quizlet page.
const fixture = `<!doctype html><html><body>
  <label>Title<input id="title" type="text" aria-label="Title"></label>
  <button type="button" id="open">Import from Word, Excel, Google Docs, etc.</button>
  <section role="dialog" aria-label="Import data" hidden id="dialog">
    <textarea id="import" aria-label="Paste your text"></textarea>
    <button type="button" id="confirm">Import</button>
  </section>
  <button type="button" id="create">Create</button>
  <script>
    window.events = {input:0, change:0, import:0, create:0};
    document.querySelector('#open').onclick = () => document.querySelector('#dialog').hidden = false;
    document.querySelector('#confirm').onclick = () => window.events.import++;
    document.querySelector('#create').onclick = () => window.events.create++;
    document.addEventListener('input', () => window.events.input++);
    document.addEventListener('change', () => window.events.change++);
  </script>
</body></html>`;

test.beforeEach(async ({ page }) => {
  await page.route('https://quizlet.com/**', route => route.fulfill({ contentType: 'text/html', body: fixture }));
  await page.goto('https://quizlet.com/create-set');
});

test('fills import and title, dispatches events, reads back without importing or publishing', async ({ page }) => {
  const result = await page.evaluate(fillQuizlet, payload);
  expect(result.ok).toBe(true);
  expect(result.titleVerified).toBe(true);
  await expect(page.locator('#title')).toHaveValue(payload.title);
  await expect(page.locator('#import')).toHaveValue(payload.tsv);
  expect(await page.evaluate(() => window.events)).toEqual({ input: 2, change: 2, import: 0, create: 0 });
});

test('refuses overwriting text or title unless explicitly authorized', async ({ page }) => {
  await page.locator('#title').fill('Existing title');
  const refused = await page.evaluate(fillQuizlet, payload);
  expect(refused.ok).toBe(false);
  await expect(page.locator('#import')).toHaveValue('');
  await expect(page.locator('#title')).toHaveValue('Existing title');
  const filled = await page.evaluate(fillQuizlet, { ...payload, overwrite: true });
  expect(filled.ok).toBe(true);
  await page.locator('#import').fill('Existing draft');
  expect((await page.evaluate(fillQuizlet, payload)).ok).toBe(false);
  await expect(page.locator('#import')).toHaveValue('Existing draft');
});

test('focused fallback handles an unknown import selector and rejects a title input', async ({ page }) => {
  await page.locator('#title').focus();
  expect((await page.evaluate(fillQuizlet, { ...payload, mode: 'focused' })).ok).toBe(false);
  await page.locator('#open').click();
  await page.locator('#dialog').evaluate(element => element.removeAttribute('aria-label'));
  await page.locator('#import').evaluate(element => element.removeAttribute('aria-label'));
  await page.locator('#import').focus();
  expect((await page.evaluate(fillQuizlet, { ...payload, mode: 'focused' })).ok).toBe(true);
  await expect(page.locator('#import')).toHaveValue(payload.tsv);
});

test('reports blocked detection and page rejections without false success', async ({ page }) => {
  await page.locator('#open').evaluate(element => element.remove());
  expect((await page.evaluate(fillQuizlet, payload)).ok).toBe(false);
  await page.locator('#dialog').evaluate(element => { element.hidden = false; });
  await page.locator('#import').evaluate(element => {
    element.addEventListener('input', () => { element.value = 'Rejected by form'; });
  });
  const rejected = await page.evaluate(fillQuizlet, payload);
  expect(rejected.ok).toBe(false);
  expect(rejected.message).toContain('讀回不一致');
});

test('does not click an inline final Import button next to an unknown textbox', async ({ page }) => {
  await page.setContent(`<textarea></textarea><button type="button" id="final">Import</button>
    <script>window.submitted=false; document.querySelector('#final').onclick=()=>window.submitted=true;</script>`);
  const result = await page.evaluate(fillQuizlet, payload);
  expect(result.ok).toBe(false);
  expect(await page.evaluate(() => window.submitted)).toBe(false);
});

test('refuses non-create routes and ambiguous controls', async ({ page }) => {
  expect((await page.evaluate(fillQuizlet, { ...payload, cardCount: 3 })).ok).toBe(false);
  await page.goto('https://quizlet.com/login');
  expect((await page.evaluate(fillQuizlet, payload)).ok).toBe(false);
  await page.goto('https://quizlet.com/create-set');
  await page.locator('#open').evaluate(element => {
    element.after(element.cloneNode(true));
  });
  expect((await page.evaluate(fillQuizlet, payload)).ok).toBe(false);
});

test('unpacked extension loads and validates local packets, retains and clears data', async () => {
  const extensionPath = path.resolve('../extension');
  const context = await chromium.launchPersistentContext('', {
    channel: 'chromium', headless: true, colorScheme: 'light',
    args: [`--disable-extensions-except=${extensionPath}`, `--load-extension=${extensionPath}`],
  });
  try {
    const worker = context.serviceWorkers()[0] ?? await context.waitForEvent('serviceworker');
    const id = new URL(worker.url()).host;
    const page = await context.newPage();
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`chrome-extension://${id}/popup.html`);
    await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(246, 247, 251)');
    await expect(page.locator('body')).toHaveCSS('color', 'rgb(46, 56, 86)');
    await expect(page.locator('header strong')).toHaveCSS('color', 'rgb(66, 85, 255)');
    await expect(page.locator('#fill')).toBeDisabled();
    await page.emulateMedia({ colorScheme: 'dark' });
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.emulateMedia({ colorScheme: 'light' });
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    const packet = {
      format: 'photo-vocabulary.quizlet', version: 1, title: payload.title,
      cards: [{ term: '<script>not executable</script>', definition: 'n. 測試', confirmed: true }],
    };
    await page.locator('#file').setInputFiles({
      name: 'quizlet-cards.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(packet)),
    });
    await expect(page.locator('#summary')).toHaveText('已載入 1 張已確認字卡');
    await expect(page.locator('#fill')).toBeEnabled();
    await expect(page.locator('#fill')).toHaveCSS('background-color', 'rgb(66, 85, 255)');
    await page.locator('#fill').hover();
    await expect(page.locator('#fill')).toHaveCSS('background-color', 'rgb(48, 63, 219)');
    await page.mouse.move(0, 0);
    await page.locator('body').screenshot({ path: 'test-results/quizlet-theme-extension.png' });
    await expect(page.locator('#tsv')).toHaveValue('<script>not executable</script>\tn. 測試');
    await page.locator('#title').fill('Theme test title');
    await page.locator('#theme-toggle').click();
    await expect(page.locator('#theme-toggle')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(10, 9, 45)');
    await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark');
    await expect(page.locator('#fill')).toHaveCSS('background-color', 'rgb(168, 177, 255)');
    await expect(page.locator('#fill')).toHaveCSS('color', 'rgb(10, 9, 45)');
    await expect(page.locator('#title')).toHaveValue('Theme test title');
    await expect(page.locator('#tsv')).toHaveValue('<script>not executable</script>\tn. 測試');
    await page.setViewportSize({ width: 390, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.locator('body').screenshot({ path: 'test-results/dark-extension.png' });
    await page.reload();
    await expect(page.locator('#theme-toggle')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#title')).toHaveValue('Theme test title');
    await expect(page.locator('#summary')).toHaveText('已載入 1 張已確認字卡');
    await page.locator('#fill').click();
    await expect(page.getByRole('alert')).toContainText('請先切到');
    await page.locator('#file').setInputFiles({
      name: 'invalid.json', mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify({ ...packet, cards: [{ ...packet.cards[0], confirmed: false }] })),
    });
    await expect(page.getByRole('alert')).toContainText('未確認');
    await expect(page.locator('#fill')).toBeDisabled();
    await page.locator('#clear').click();
    await expect(page.locator('#summary')).toHaveText('尚未載入字卡');
    await page.reload();
    await expect(page.locator('#fill')).toBeDisabled();
    await expect(page.locator('#theme-toggle')).toHaveAttribute('aria-pressed', 'true');
    await page.locator('#theme-toggle').click();
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.reload();
    await expect(page.locator('#theme-toggle')).toHaveAttribute('aria-pressed', 'false');
    await expect(page.locator('html')).toHaveCSS('color-scheme', 'light');
    await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(246, 247, 251)');
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

test('real activeTab action injects the packaged adapter in an isolated world', async () => {
  const extensionPath = path.resolve('../extension');
  const context = await chromium.launchPersistentContext('', {
    channel: 'chromium', headless: true,
    args: [`--disable-extensions-except=${extensionPath}`, `--load-extension=${extensionPath}`,
      '--enable-unsafe-extension-debugging'],
  });
  try {
    const worker = context.serviceWorkers()[0] ?? await context.waitForEvent('serviceworker');
    const id = new URL(worker.url()).host;
    const quizlet = await context.newPage();
    await quizlet.route('https://quizlet.com/**', route =>
      route.fulfill({ contentType: 'text/html', body: fixture }));
    await quizlet.goto('https://quizlet.com/create-set');
    const browserSession = await context.browser()!.newBrowserCDPSession();
    const { targetInfos } = await browserSession.send('Target.getTargets', { filter: [{ type: 'tab' }] });
    const tab = targetInfos.find(target => target.url === 'https://quizlet.com/create-set');
    expect(tab).toBeDefined();
    await browserSession.send('Extensions.triggerAction', { id, targetId: tab!.targetId });
    const extensionPage = await context.newPage();
    await extensionPage.goto(`chrome-extension://${id}/popup.html`);
    await extensionPage.locator('#file').setInputFiles({
      name: 'confirmed.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({
        format: 'photo-vocabulary.quizlet', version: 1, title: payload.title,
        cards: [{ term: 'conserve', definition: 'v. 節省；保護', confirmed: true },
          { term: 'habitat', definition: 'n. 棲息地', confirmed: true }],
      })),
    });
    await expect(extensionPage.locator('#fill')).toBeEnabled();
    await extensionPage.locator('#title').fill('Edited extension title');
    await extensionPage.locator('#title').blur();
    await quizlet.bringToFront();
    // Run the popup's real handler without activating its test-only extension tab.
    await extensionPage.locator('#fill').evaluate(button => button.click());
    await expect(extensionPage.locator('#status')).toContainText('已填入並讀回核對 2 張');
    await expect(quizlet.locator('#import')).toHaveValue(payload.tsv);
    await expect(quizlet.locator('#title')).toHaveValue('Edited extension title');
    expect(await quizlet.evaluate(() => window.events.import + window.events.create)).toBe(0);
    await quizlet.goto('https://quizlet.com/login');
    await extensionPage.locator('#fill').evaluate(button => button.click());
    await expect(extensionPage.getByRole('alert')).toContainText('請先切到');
  } finally {
    await context.close();
  }
});
