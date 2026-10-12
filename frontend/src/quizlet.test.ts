import { describe, expect, it } from 'vitest';
import { createQuizletPacket } from './quizlet';
import { packetTsv } from '../../extension/packet.js';
import type { Validation } from './types';

const validation: Validation = {
  valid: true, issues: [], missedBlockIds: [], selectedCount: 2,
  tsv: 'conserve\tv. 節省；保護\nhabitat\tn. 棲息地',
};

describe('confirmed extension export', () => {
  it('exports exactly the validated TSV with confirmation and no photos', () => {
    const packet = createQuizletPacket(validation, 'My words');
    expect(packet.cards).toHaveLength(2);
    expect(packet.cards.every(card => card.confirmed)).toBe(true);
    expect(packetTsv(packet)).toBe(validation.tsv);
    expect(Object.keys(packet)).toEqual(['format', 'version', 'title', 'cards']);
  });
  it('rejects unvalidated output, invalid counts and malformed rows', () => {
    expect(() => createQuizletPacket({ ...validation, valid: false }, 'Title')).toThrow();
    expect(() => createQuizletPacket({ ...validation, selectedCount: 3 }, 'Title')).toThrow();
    expect(() => createQuizletPacket({ ...validation, tsv: 'one\tdef\textra' }, 'Title')).toThrow();
    expect(() => createQuizletPacket(validation, ' ')).toThrow();
  });
});
