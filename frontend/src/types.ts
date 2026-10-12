export type Crop = { x: number; y: number; width: number; height: number };
export type Photo = { imageId: string; width: number; height: number; previewUrl: string };
export type Block = {
  id: string; text: string; bbox: [number, number, number, number]; ocr_score: number;
  original_text?: string | null;
};
export type Card = {
  id: string;
  term: string;
  part_of_speech: string;
  definition: string;
  example: string;
  source_block_ids: string[];
  definitionOrigin: 'photo' | 'model' | 'manual' | 'missing';
  partOfSpeechOrigin?: 'photo' | 'model' | 'manual' | 'missing';
  needs_review: boolean;
  review_reason: string | null;
  selected: boolean;
  confirmed: boolean;
};
export type Extraction = {
  id: string;
  imageId: string;
  status: 'queued' | 'preprocessing' | 'recognizing' | 'structuring' | 'completed' | 'failed';
  ocr_blocks: Block[];
  draft_cards: Card[];
  reviewed_cards?: Card[];
  warnings: string[];
  error: string | null;
  processedUrl?: string;
  transform?: { processedSize: [number, number] };
  settings: { rotation: 0 | 90 | 180 | 270; crop: Crop | null; layout: 'auto' | 'single' | 'double' };
  elapsedMs: number;
  cacheHit: boolean;
};
export type Health = {
  ocrReady: boolean; ocrMessage: string; modelConfigured: boolean;
  modelMessage: string;
  metrics: { ocrCalls: number; modelCalls: number; cacheHits: number };
};
export type Validation = {
  valid: boolean;
  issues: { cardId: string; errors: string[]; warnings: string[]; blocking: boolean }[];
  missedBlockIds: string[];
  selectedCount: number;
  tsv: string;
};
export type Library = {
  images: { id: string; width: number; height: number; previewUrl: string }[];
  extractions: Pick<Extraction, 'id' | 'imageId' | 'status'>[];
};
