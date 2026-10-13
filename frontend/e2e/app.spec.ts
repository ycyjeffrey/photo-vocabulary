import { expect, test } from '@playwright/test';
import path from 'node:path';

test.use({ colorScheme: 'light' });

test('English-left Chinese-right layout pairs, exports and restores dog with 狗', async ({ page, request }) => {
  const photo = await request.post('/v1/images', {
    multipart: { file: { name: 'bilingual.png', mimeType: 'image/png',
      buffer: await (await import('node:fs/promises')).readFile(path.resolve('../.local/demo/bilingual.png')) } },
  });
  const { imageId } = await photo.json();
  try {
    await page.goto('/');
    await page.getByLabel('開啟已儲存照片').selectOption(imageId);
    await page.getByRole('combobox', { name: '版面', exact: true }).selectOption('eng-zh');
    await expect(page.getByText('請裁切到英中分隔位於圖片中央。', { exact: false })).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.getByRole('button', { name: '擷取單字', exact: true }).click();
    await expect(page.locator('.vocab-card')).toHaveCount(3, { timeout: 30000 });
    await expect(page.getByLabel('單字 card-1')).toHaveValue('dog');
    await expect(page.getByLabel('釋義 card-1')).toHaveValue('狗');
    await expect(page.getByLabel('釋義 card-2')).toHaveValue('貓');
    await page.getByLabel('選取 cat', { exact: true }).uncheck();
    await page.getByLabel('選取 bird', { exact: true }).uncheck();
    await page.getByLabel('確認 dog', { exact: true }).check();
    await page.getByRole('button', { name: '驗證並產生 TSV' }).click();
    await expect(page.getByLabel('Quizlet TSV')).toHaveValue('dog\t狗');
    await page.reload();
    await page.getByLabel('開啟已儲存照片').selectOption(imageId);
    await expect(page.getByRole('combobox', { name: '版面', exact: true })).toHaveValue('eng-zh');
    await expect(page.getByLabel('釋義 card-1')).toHaveValue('狗');
  } finally {
    await request.delete(`/v1/images/${imageId}`);
  }
});

test('theme follows the system until chosen, persists, and reports unavailable storage', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/');
  const toggle = page.getByRole('button', { name: '深色模式', exact: true });
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(10, 9, 45)');
  await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark');
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#0a092d');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await toggle.focus();
  await page.keyboard.press('Enter');
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await toggle.click();
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.reload();
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('html')).toHaveCSS('color-scheme', 'light');
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#4255ff');

  await page.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new Error('Storage blocked'); };
    Storage.prototype.setItem = () => { throw new Error('Storage blocked'); };
  });
  await page.reload();
  await expect(page.getByRole('status')).toContainText('無法讀取外觀設定');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('status')).toContainText('無法儲存');
});

test('photo → source review → correction → saved TSV → deletion', async ({ page, request, context }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const imageIds: string[] = [];
  page.on('response', async response => {
    if (response.url().endsWith('/v1/images') && response.request().method() === 'POST' && response.ok()) {
      imageIds.push((await response.json()).imageId);
    }
  });
  try {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: '拍下單字，留下所學。' })).toBeVisible();
    await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(246, 247, 251)');
    await expect(page.locator('body')).toHaveCSS('color', 'rgb(46, 56, 86)');
    await expect(page.locator('.brand-icon')).toHaveCSS('background-color', 'rgb(66, 85, 255)');
    await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#4255ff');
    await page.getByLabel('上傳單字表照片').setInputFiles(path.resolve('../.local/demo/single.png'));
    await expect(page.getByRole('button', { name: '擷取單字', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: '擷取單字', exact: true }))
      .toHaveCSS('background-color', 'rgb(66, 85, 255)');
    await page.getByRole('button', { name: '擷取單字', exact: true }).click();
    await expect(page.locator('.vocab-card')).toHaveCount(3, { timeout: 30000 });
    await page.getByRole('button', { name: '查看來源' }).first().click();
    await expect(page.locator('.source-box').first()).toBeVisible();
    const library = await (await request.get('/v1/library')).json();
    const jobId = library.extractions.find((item: { imageId: string }) => item.imageId === imageIds[0]).id;
    const extraction = await (await request.get(`/v1/extractions/${jobId}`)).json();
    const source = extraction.ocr_blocks.find((block: { id: string }) =>
      block.id === extraction.draft_cards[0].source_block_ids[0]);
    const canvas = await page.locator('.photo-stage canvas').boundingBox();
    const overlay = await page.locator('.source-box').first().boundingBox();
    expect(canvas).not.toBeNull();
    expect(overlay).not.toBeNull();
    expect(Math.abs(overlay!.x - canvas!.x - source.bbox[0] / extraction.transform.processedSize[0] * canvas!.width)).toBeLessThan(1);
    expect(Math.abs(overlay!.y - canvas!.y - source.bbox[1] / extraction.transform.processedSize[1] * canvas!.height)).toBeLessThan(1);
    await expect(page.getByLabel('單字 card-1')).toHaveValue('conserve');
    await expect(page.getByLabel('釋義 card-1')).toHaveValue('節省;保護');

    // A card is never exportable merely because OCR selected it.
    await page.getByRole('button', { name: '驗證並產生 TSV' }).click();
    await expect(page.getByRole('alert')).toContainText('確認所有選取字卡');
    await expect(page.getByLabel('Quizlet TSV')).toHaveCount(0);
    await page.getByRole('button', { name: '關閉', exact: true }).click();

    for (const term of ['conserve', 'habitat', 'resource']) {
      await page.getByLabel(`確認 ${term}`, { exact: true }).check();
    }
    await page.getByRole('button', { name: '驗證並產生 TSV' }).click();
    await expect(page.getByLabel('Quizlet TSV')).toHaveValue(
      'conserve\tv. 節省;保護\nhabitat\tn. 棲息地\nresource\tn. 資源',
    );
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.getByRole('button', { name: '複製 TSV', exact: true }).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
      'conserve\tv. 節省;保護\nhabitat\tn. 棲息地\nresource\tn. 資源',
    );
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '下載 TSV', exact: true }).click();
    const downloaded = await downloadPromise;
    expect(downloaded.suggestedFilename()).toBe('vocabulary.tsv');
    const stream = await downloaded.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream) chunks.push(Buffer.from(chunk));
    expect(Buffer.concat(chunks).toString('utf8')).toBe(
      'conserve\tv. 節省;保護\nhabitat\tn. 棲息地\nresource\tn. 資源',
    );
    await page.getByText('使用 Chrome 擴充功能協助填入 Quizlet', { exact: true }).click();
    await page.getByLabel('字卡集標題', { exact: true }).fill('Conservation vocabulary');
    const jsonDownloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '下載擴充功能 JSON', exact: true }).click();
    const jsonDownload = await jsonDownloadPromise;
    expect(jsonDownload.suggestedFilename()).toBe('quizlet-cards.json');
    const jsonChunks: Buffer[] = [];
    for await (const chunk of await jsonDownload.createReadStream()) jsonChunks.push(Buffer.from(chunk));
    const packet = JSON.parse(Buffer.concat(jsonChunks).toString('utf8'));
    expect(packet).toEqual({
      format: 'photo-vocabulary.quizlet', version: 1, title: 'Conservation vocabulary',
      cards: [
        { term: 'conserve', definition: 'v. 節省;保護', confirmed: true },
        { term: 'habitat', definition: 'n. 棲息地', confirmed: true },
        { term: 'resource', definition: 'n. 資源', confirmed: true },
      ],
    });
    await page.getByLabel('釋義 card-3').fill('自然資源');
    await page.getByRole('button', { name: '深色模式', exact: true }).click();
    await expect(page.getByLabel('釋義 card-3')).toHaveValue('自然資源');
    await expect(page.locator('body')).toHaveCSS('color', 'rgb(246, 247, 251)');
    await expect(page.locator('.brand-icon')).toHaveCSS('color', 'rgb(10, 9, 45)');
    await expect(page.getByLabel('確認 resource', { exact: true })).not.toBeChecked();
    await expect(page.getByLabel('Quizlet TSV')).toHaveCount(0);
    await page.getByLabel('確認 resource', { exact: true }).check();
    await page.getByRole('button', { name: '儲存修改', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('修改已儲存');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.getByLabel('開啟已儲存照片').selectOption(imageIds[0]);
    await expect(page.getByLabel('釋義 card-3')).toHaveValue('自然資源');
    await expect(page.getByLabel('確認 resource', { exact: true })).toBeChecked();
    await page.getByRole('button', { name: '驗證並產生 TSV' }).click();
    await expect(page.getByLabel('Quizlet TSV')).toContainText('resource\tn. 自然資源');
    await page.screenshot({ path: 'test-results/review-desktop.png', fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole('button', { name: '複製 TSV', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: 'test-results/review-mobile.png', fullPage: true });
    await page.setViewportSize({ width: 320, height: 740 });
    await expect(page.getByRole('button', { name: '深色模式', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: '刪除此照片與辨識資料' }).click();
    await expect(page.getByRole('status')).toContainText('已從本機刪除');
    expect(errors).toEqual([]);
  } finally {
    for (const id of imageIds) await request.delete(`/v1/images/${id}`);
  }
});

test('wrapped definitions, uncertain exclusions and manual card recovery', async ({ page, request }) => {
  const photo = await request.post('/v1/images', {
    multipart: { file: { name: 'wrapped.png', mimeType: 'image/png',
      buffer: await (await import('node:fs/promises')).readFile(path.resolve('../.local/demo/wrapped.png')) } },
  });
  const { imageId } = await photo.json();
  try {
    await page.goto('/');
    await page.getByLabel('開啟已儲存照片').selectOption(imageId);
    await page.getByRole('button', { name: '擷取單字', exact: true }).click();
    await expect(page.locator('.vocab-card')).toHaveCount(3, { timeout: 30000 });
    await expect(page.getByLabel('釋義 card-1')).toHaveValue('節省;保護');
    await expect(page.getByLabel('選取 resource', { exact: true })).not.toBeChecked();
    await expect(page.getByLabel('選取 resource', { exact: true })).toBeDisabled();
    await page.getByLabel('釋義 card-3').fill('資源');
    await page.getByLabel('確認 resource', { exact: true }).check();
    await page.getByRole('button', { name: '刪除 habitat', exact: true }).click();
    await expect(page.locator('.vocab-card')).toHaveCount(2);
    await page.getByRole('button', { name: '新增漏掉的單字' }).click();
    const manual = page.locator('.vocab-card').last();
    await manual.getByLabel(/單字 /).fill('look after');
    await manual.getByLabel(/釋義 /).fill('照顧');
    await page.getByLabel('確認 look after', { exact: true }).check();
    await page.getByLabel('確認 conserve', { exact: true }).check();
    await page.getByRole('button', { name: '驗證並產生 TSV' }).click();
    await expect(page.getByLabel('Quizlet TSV')).toHaveValue(
      'conserve\tv. 節省;保護\nresource\tn. 資源\nlook after\t照顧',
    );
  } finally {
    await request.delete(`/v1/images/${imageId}`);
  }
});

test('rotation, keyboard crop, layout and cache', async ({ page, request }) => {
  const photo = await request.post('/v1/images', {
    multipart: { file: { name: 'double.png', mimeType: 'image/png',
      buffer: await (await import('node:fs/promises')).readFile(path.resolve('../.local/demo/double.png')) } },
  });
  const { imageId } = await photo.json();
  try {
    await page.goto('/');
    await page.getByLabel('開啟已儲存照片').selectOption(imageId);
    await page.getByRole('button', { name: '旋轉 90°' }).click();
    await page.getByRole('button', { name: '旋轉 90°' }).click();
    await page.getByRole('button', { name: '旋轉 90°' }).click();
    await page.getByRole('button', { name: '旋轉 90°' }).click();
    await page.getByLabel('裁切寬').fill('50');
    await page.getByRole('combobox', { name: '版面', exact: true }).selectOption('single');
    await page.getByRole('button', { name: '擷取單字', exact: true }).click();
    await expect(page.locator('.vocab-card')).toHaveCount(3, { timeout: 30000 });
    await page.getByRole('button', { name: '擷取單字', exact: true }).click();
    await expect(page.getByText('本次命中快取', { exact: true })).toBeVisible();
  } finally {
    await request.delete(`/v1/images/${imageId}`);
  }
});
