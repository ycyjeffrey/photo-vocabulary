export type QuizletPacket = {
  format: 'photo-vocabulary.quizlet';
  version: 1;
  title: string;
  cards: { term: string; definition: string; confirmed: true }[];
};
export const MAX_PACKET_BYTES: number;
export const MAX_CARDS: number;
export function cleanField(value: string): string;
export function validatePacket(value: unknown): QuizletPacket;
export function parsePacket(text: string): QuizletPacket;
export function packetTsv(packet: QuizletPacket): string;
export function isQuizletCreateUrl(value: string): boolean;
