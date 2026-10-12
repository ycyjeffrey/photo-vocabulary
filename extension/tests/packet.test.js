import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { MAX_PACKET_BYTES, isQuizletCreateUrl, parsePacket, packetTsv, validatePacket } from '../packet.js';

const packet = {
  format: 'photo-vocabulary.quizlet', version: 1, title: 'My vocabulary',
  cards: [{ term: 'conserve', definition: 'v. 節省；保護', confirmed: true }],
};

test('confirmed packet produces exact TSV and contains only export fields', () => {
  const loaded = validatePacket({ ...packet, imageUrl: '/private.png',
    cards: [{ ...packet.cards[0], source_block_ids: ['b1'], definitionOrigin: 'model' }] });
  assert.equal(packetTsv(loaded), 'conserve\tv. 節省；保護');
  assert.deepEqual(loaded, packet);
});

test('normalizes field delimiters without altering spelling or Chinese text', () => {
  const input = structuredClone(packet);
  input.cards[0].term = 'look\tafter';
  input.cards[0].definition = 'phr.\r\n照顧';
  assert.equal(packetTsv(input), 'look after\tphr. 照顧');
});

test('rejects malformed, unconfirmed, empty and oversized packets', () => {
  for (const value of [null, {}, [], { ...packet, version: 2 }, { ...packet, cards: [] },
    { ...packet, cards: Array(501).fill(packet.cards[0]) }, { ...packet, title: ' ' },
    { ...packet, title: 'x'.repeat(201) },
    { ...packet, cards: [{ ...packet.cards[0], confirmed: false }] },
    { ...packet, cards: [{ ...packet.cards[0], confirmed: 'true' }] },
    { ...packet, cards: [{ ...packet.cards[0], term: ' \n' }] },
    { ...packet, cards: [{ ...packet.cards[0], definition: '' }] },
    { ...packet, cards: [{ ...packet.cards[0], term: 'x'.repeat(301) }] }]) {
    assert.throws(() => validatePacket(value));
  }
  assert.throws(() => parsePacket('{broken'));
  assert.throws(() => parsePacket(' '.repeat(MAX_PACKET_BYTES + 1)));
});

test('only accepts HTTPS Quizlet create-set routes', () => {
  for (const url of ['https://quizlet.com/create-set', 'https://www.quizlet.com/create-set/',
    'https://quizlet.com/zh-tw/create-set?source=local', 'https://quizlet.com/en/create-set']) {
    assert.equal(isQuizletCreateUrl(url), true);
  }
  for (const url of ['https://quizlet.com.evil.example/create-set', 'http://quizlet.com/create-set',
    'https://quizlet.com/login', 'https://evil.example/?quizlet.com/create-set',
    'https://quizlet.com/123/edit', 'not a URL']) {
    assert.equal(isQuizletCreateUrl(url), false);
  }
});

test('manifest grants no blanket host access or remote scripts', async () => {
  const manifest = JSON.parse(await readFile(new URL('../manifest.json', import.meta.url), 'utf8'));
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions, ['activeTab', 'scripting', 'storage', 'clipboardWrite']);
  assert.equal(manifest.host_permissions, undefined);
  assert.equal(manifest.content_scripts, undefined);
  assert.equal(manifest.externally_connectable, undefined);
  assert.equal(manifest.content_security_policy.extension_pages, "script-src 'self'; object-src 'none'");
});
