export const MAX_PACKET_BYTES = 2 * 1024 * 1024;
export const MAX_CARDS = 500;

export function cleanField(value) {
  return value.replace(/[\t\r\n]+/g, ' ').trim();
}

export function validatePacket(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      value.format !== 'photo-vocabulary.quizlet' || value.version !== 1 ||
      typeof value.title !== 'string' || !value.title.trim() || value.title.length > 200 ||
      !Array.isArray(value.cards) || value.cards.length < 1 || value.cards.length > MAX_CARDS) {
    throw new Error('不是有效的字拾匯入檔（版本 1，1–500 張字卡）。請從本機 app 重新匯出。');
  }
  const cards = value.cards.map((card, index) => {
    if (!card || typeof card !== 'object' || card.confirmed !== true ||
        typeof card.term !== 'string' || typeof card.definition !== 'string' ||
        card.term.length > 300 || card.definition.length > 3200 ||
        !cleanField(card.term) || !cleanField(card.definition)) {
      throw new Error(`第 ${index + 1} 張字卡未確認、缺少內容或超過長度限制。`);
    }
    return { term: cleanField(card.term), definition: cleanField(card.definition), confirmed: true };
  });
  return { format: 'photo-vocabulary.quizlet', version: 1, title: cleanField(value.title), cards };
}

export function parsePacket(text) {
  if (new TextEncoder().encode(text).length > MAX_PACKET_BYTES) {
    throw new Error('匯入檔超過 2 MB。');
  }
  let value;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error('無法讀取 JSON。請選擇 app 下載的 quizlet-cards.json。');
  }
  return validatePacket(value);
}

export function packetTsv(packet) {
  return validatePacket(packet).cards.map(card => `${card.term}\t${card.definition}`).join('\n');
}

export function isQuizletCreateUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && ['quizlet.com', 'www.quizlet.com'].includes(url.hostname) &&
      /^\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?create-set\/?$/i.test(url.pathname);
  } catch {
    return false;
  }
}
