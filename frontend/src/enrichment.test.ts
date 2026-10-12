import { describe, expect, it } from 'vitest';
import { canEnrich } from './enrichment';
import type { Card } from './types';

const card: Card = {
  id: 'one', term: 'resource', definition: '資源', part_of_speech: '',
  example: '', source_block_ids: ['b1'], definitionOrigin: 'photo',
  needs_review: false, review_reason: null, selected: false, confirmed: true,
};

describe('enrichment eligibility', () => {
  it('allows POS-only, definition-only and both missing', () => {
    expect(canEnrich(card)).toBe(true);
    expect(canEnrich({ ...card, definition: '', part_of_speech: 'n.' })).toBe(true);
    expect(canEnrich({ ...card, definition: '' })).toBe(true);
    expect(canEnrich({ ...card, part_of_speech: 'n.' })).toBe(false);
  });
  it('requires a confirmed, nonempty English term', () => {
    expect(canEnrich({ ...card, confirmed: false })).toBe(false);
    expect(canEnrich({ ...card, term: ' ' })).toBe(false);
  });
  it('protects original fields, even if manually cleared', () => {
    expect(canEnrich(card, { ...card, part_of_speech: 'n.' })).toBe(false);
    expect(canEnrich({ ...card, definition: '' }, { ...card, part_of_speech: 'n.' })).toBe(false);
    expect(canEnrich({ ...card, definition: '' }, card)).toBe(true);
  });
});
