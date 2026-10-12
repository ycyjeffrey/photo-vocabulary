import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolveTheme } from '../theme.js';

const theme = await readFile(new URL('../theme.css', import.meta.url), 'utf8');
const palettes = [...theme.matchAll(/:root(?:\[data-theme="dark"\])?\s*\{([^}]+)\}/g)]
  .map(block => Object.fromEntries([...block[1].matchAll(/--([\w-]+):\s*(#[\da-f]+);/gi)]
    .map(match => [match[1], match[2].toLowerCase()])));
const [colors, dark] = palettes;

test('theme selection respects a saved choice before the OS preference', () => {
  assert.equal(resolveTheme('light', true), 'light');
  assert.equal(resolveTheme('dark', false), 'dark');
  assert.equal(resolveTheme(null, true), 'dark');
  assert.equal(resolveTheme(undefined, false), 'light');
  assert.equal(resolveTheme('invalid', true), 'dark');
});

test('both palettes define valid, matching color tokens', () => {
  assert.equal(palettes.length, 2);
  assert.deepEqual(Object.keys(dark).sort(), Object.keys(colors).sort());
  for (const palette of palettes) {
    for (const value of Object.values(palette)) assert.match(value, /^#(?:[\da-f]{6}|[\da-f]{8})$/);
  }
});

function luminance(hex) {
  const channels = hex.slice(1).match(/../g).map(channel => {
    const value = parseInt(channel, 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

test('app and extension use the same local blue/navy theme', async () => {
  assert.equal(colors.primary, '#4255ff');
  assert.equal(colors.text, '#2e3856');
  assert.equal(colors.page, '#f6f7fb');
  const app = await readFile(new URL('../../frontend/src/styles.css', import.meta.url), 'utf8');
  const popup = await readFile(new URL('../popup.css', import.meta.url), 'utf8');
  assert.match(app, /@import '\.\.\/\.\.\/extension\/theme\.css'/);
  assert.match(popup, /@import '\.\/theme\.css'/);
  assert.doesNotMatch(app + popup, /#[\da-f]{3,8}\b|--green\b/i);
  const tokenNames = new Set([...theme.matchAll(/--([\w-]+):/g)].map(match => match[1]));
  for (const match of (app + popup).matchAll(/var\(--([\w-]+)\)/g)) {
    assert.ok(tokenNames.has(match[1]), `Undefined theme token: ${match[1]}`);
  }
  const html = await readFile(new URL('../../frontend/index.html', import.meta.url), 'utf8');
  assert.match(html, /name="theme-color" content="#4255ff"/);
});

test('theme text pairs meet WCAG AA contrast for normal text', () => {
  const pairs = [
    ['on-primary', 'primary'], ['on-primary', 'primary-hover'],
    ['text', 'surface'], ['text', 'page'], ['text', 'primary-soft'],
    ['muted', 'surface'], ['muted', 'page'], ['muted', 'primary-soft'],
    ['primary', 'surface'], ['primary-hover', 'primary-soft'],
    ['success', 'success-soft'], ['warning', 'warning-soft'],
    ['error', 'error-soft'], ['error', 'surface'], ['error', 'page'],
    ['model', 'surface'], ['warning', 'surface'],
  ];
  for (const [index, palette] of palettes.entries()) {
    for (const [foreground, background] of pairs) {
      const values = [luminance(palette[foreground]), luminance(palette[background])].sort((a, b) => b - a);
      const contrast = (values[0] + 0.05) / (values[1] + 0.05);
      assert.ok(contrast >= 4.5, `Theme ${index}: ${foreground} on ${background}: ${contrast.toFixed(2)} < 4.5`);
    }
  }
});
