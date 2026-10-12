import { MAX_PACKET_BYTES, isQuizletCreateUrl, parsePacket, packetTsv, validatePacket } from './packet.js';
import { fillQuizlet } from './quizlet.js';

const ui = Object.fromEntries(['file', 'title', 'summary', 'overwrite', 'open', 'fill', 'focused', 'tsv', 'copy', 'clear', 'status']
  .map(id => [id, document.getElementById(id)]));
let packet = null;
let busy = false;

function status(message, error = false) {
  ui.status.textContent = message;
  ui.status.className = error ? 'error' : '';
  ui.status.setAttribute('role', error ? 'alert' : 'status');
}

function render() {
  for (const id of ['title', 'fill', 'focused', 'copy']) ui[id].disabled = busy || !packet;
  for (const id of ['file', 'clear', 'open', 'overwrite']) ui[id].disabled = busy;
  ui.summary.textContent = packet ? `已載入 ${packet.cards.length} 張已確認字卡` : '尚未載入字卡';
  ui.tsv.value = packet ? packetTsv(packet) : '';
}

async function run(operation) {
  if (busy) return;
  busy = true;
  status('');
  render();
  try {
    await operation();
  } catch (error) {
    status(error instanceof Error ? error.message : String(error), true);
  } finally {
    busy = false;
    render();
  }
}

ui.file.addEventListener('change', () => run(async () => {
  const file = ui.file.files[0];
  if (!file) return;
  // A rejected replacement must not leave an older packet armed for accidental import.
  await chrome.storage.local.remove('packet');
  packet = null;
  ui.title.value = '';
  ui.overwrite.checked = false;
  if (file.size > MAX_PACKET_BYTES) throw new Error('JSON 檔案不可超過 2 MB。');
  const loaded = parsePacket(await file.text());
  await chrome.storage.local.set({ packet: loaded });
  packet = loaded;
  ui.title.value = packet.title;
  ui.overwrite.checked = false;
  status('已載入。請切到已登入的 Quizlet 建立頁，再開啟本擴充功能填入。');
}).finally(() => { ui.file.value = ''; }));

async function currentPacket() {
  if (!packet) throw new Error('請先載入已確認字卡的 JSON。');
  const next = validatePacket({ ...packet, title: ui.title.value });
  packet = next;
  await chrome.storage.local.set({ packet: next });
  return next;
}

async function fill(mode) {
  await run(async () => {
    const loaded = await currentPacket();
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !isQuizletCreateUrl(tab.url)) {
      throw new Error('請先切到 https://quizlet.com/create-set，登入並開啟建立字卡集頁面，再點擊擴充功能。');
    }
    status('正在填入與核對；請保持面板開啟…');
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: fillQuizlet,
      args: [{ title: loaded.title, tsv: packetTsv(loaded), cardCount: loaded.cards.length,
        mode, overwrite: ui.overwrite.checked }],
    });
    const result = results[0]?.result;
    if (!result?.ok) throw new Error(result?.message || '未收到 Quizlet 頁面回應，請重新整理後再試。');
    status(result.message);
  });
}

ui.fill.addEventListener('click', () => fill('auto'));
ui.focused.addEventListener('click', () => fill('focused'));
ui.copy.addEventListener('click', () => run(async () => {
  const loaded = await currentPacket();
  await navigator.clipboard.writeText(packetTsv(loaded));
  status(`已複製 ${loaded.cards.length} 張字卡的 TSV。請貼到 Quizlet Import。`);
}));
ui.open.addEventListener('click', () => run(async () => {
  await chrome.tabs.create({ url: 'https://quizlet.com/create-set' });
}));
ui.clear.addEventListener('click', () => run(async () => {
  await chrome.storage.local.remove('packet');
  packet = null;
  ui.title.value = '';
  ui.overwrite.checked = false;
  status('已清除擴充功能儲存的字卡；本機 app 與 Quizlet 內容不變。');
}));
ui.title.addEventListener('change', () => {
  void currentPacket().catch(error => status(error instanceof Error ? error.message : String(error), true));
});

await run(async () => {
  const stored = await chrome.storage.local.get('packet');
  if (stored.packet) {
    packet = validatePacket(stored.packet);
    ui.title.value = packet.title;
  }
});
