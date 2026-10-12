import type { Card } from './types';

export function canEnrich(card: Card, original?: Card): boolean {
  return card.confirmed && !!card.term.trim() && (
    (!card.definition.trim() && !original?.definition.trim()) ||
    (!card.part_of_speech.trim() && !original?.part_of_speech.trim())
  );
}
