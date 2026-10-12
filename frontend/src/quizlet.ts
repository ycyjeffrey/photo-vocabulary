import { parsePacket, type QuizletPacket } from '../../extension/packet.js';
import type { Validation } from './types';

export function createQuizletPacket(validation: Validation, title: string): QuizletPacket {
  if (!validation.valid || !validation.tsv || validation.selectedCount < 1) {
    throw new Error('請先驗證並確認要匯出的字卡。');
  }
  const cards = validation.tsv.split('\n').map(line => {
    const fields = line.split('\t');
    if (fields.length !== 2) throw new Error('TSV 格式不正確，請重新驗證字卡。');
    return { term: fields[0], definition: fields[1], confirmed: true };
  });
  if (cards.length !== validation.selectedCount) throw new Error('字卡數量不一致，請重新驗證。');
  return parsePacket(JSON.stringify({ format: 'photo-vocabulary.quizlet', version: 1, title, cards }));
}
