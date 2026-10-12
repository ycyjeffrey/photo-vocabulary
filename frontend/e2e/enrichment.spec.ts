import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

test('local model fills missing POS and definitions without replacing existing fields', async ({ page, request }) => {
  test.skip(process.env.RUN_MODEL_TESTS !== '1', 'Set RUN_MODEL_TESTS=1 with a configured local model');
  test.setTimeout(180000);
  const photo = await request.post('/v1/images', {
    multipart: { file: { name: 'pos-enrichment-test.png', mimeType: 'image/png',
      buffer: await readFile(path.resolve('../.local/demo/wrapped.png')) } },
  });
  expect(photo.ok()).toBe(true);
  const { imageId } = await photo.json();
  try {
    await page.goto('/');
    await page.getByLabel('開啟已儲存照片').selectOption(imageId);
    await page.getByRole('button', { name: '擷取單字', exact: true }).click();
    await expect(page.locator('.vocab-card')).toHaveCount(3, { timeout: 30000 });
    const photoDefinition = await page.getByLabel('釋義 card-1').inputValue();
    await page.getByLabel('確認 resource', { exact: true }).check();
    await page.getByRole('button', { name: '新增漏掉的單字' }).click();
    const both = page.locator('.vocab-card').nth(3);
    await both.getByLabel(/單字 /).fill('happy');
    await page.getByLabel('確認 happy', { exact: true }).check();
    await page.getByRole('button', { name: '新增漏掉的單字' }).click();
    const posOnly = page.locator('.vocab-card').nth(4);
    await posOnly.getByLabel(/單字 /).fill('quickly');
    await posOnly.getByLabel(/釋義 /).fill('迅速地（手動校正）');
    await page.getByLabel('確認 quickly', { exact: true }).check();

    const button = page.getByRole('button', { name: '補上詞性／中文釋義（本機模型）', exact: true });
    await expect(button).toBeEnabled();
    const responsePromise = page.waitForResponse(r => r.url().endsWith('/v1/cards/enrich'), { timeout: 150000 });
    await button.click();
    const response = await responsePromise;
    expect(response.ok(), await response.text()).toBe(true);
    await expect(both.getByLabel(/詞性 /)).toHaveValue('adj.');
    await expect(posOnly.getByLabel(/詞性 /)).toHaveValue('adv.');
    await expect(posOnly.getByLabel(/釋義 /)).toHaveValue('迅速地（手動校正）');
    await expect(page.getByLabel('詞性 card-3')).toHaveValue('n.');
    await expect(page.getByLabel('釋義 card-3')).not.toHaveValue('');
    await expect(page.getByLabel('釋義 card-1')).toHaveValue(photoDefinition);
    await expect(page.locator('.pos-origin.model')).toHaveCount(2);
    for (const term of ['happy', 'quickly', 'resource']) {
      await expect(page.getByLabel(`確認 ${term}`, { exact: true })).not.toBeChecked();
      await expect(page.getByLabel(`選取 ${term}`, { exact: true })).not.toBeChecked();
      await page.getByLabel(`確認 ${term}`, { exact: true }).check();
    }
    await page.getByRole('button', { name: '我已核對，確認已選字卡' }).click();
    await page.getByRole('button', { name: '驗證並產生 TSV' }).click();
    await expect(page.getByLabel('Quizlet TSV')).toContainText('quickly\tadv. 迅速地（手動校正）');
    await expect(page.getByLabel('Quizlet TSV')).toContainText('happy\tadj. ');
    await page.reload();
    await page.getByLabel('開啟已儲存照片').selectOption(imageId);
    await expect(page.locator('.pos-origin.model')).toHaveCount(2);
    await expect(page.locator('.vocab-card').nth(4).getByLabel(/詞性 /)).toHaveValue('adv.');
    await expect(button).toBeDisabled();
  } finally {
    const deleted = await request.delete(`/v1/images/${imageId}`);
    expect(deleted.ok()).toBe(true);
  }
});
