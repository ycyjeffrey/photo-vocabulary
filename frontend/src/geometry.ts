import type { Crop } from './types';

export function cropFromPoints(start: [number, number], end: [number, number]): Crop {
  const clamp = (value: number) => Math.max(0, Math.min(1, value));
  const [x1, y1] = start.map(clamp);
  const [x2, y2] = end.map(clamp);
  return { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1) };
}
