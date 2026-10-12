import { describe, expect, it } from 'vitest';
import { cropFromPoints } from './geometry';

describe('crop coordinates', () => {
  it('normalizes either drag direction', () => {
    expect(cropFromPoints([0.75, 0.8], [0.25, 0.2])).toEqual({
      x: 0.25, y: 0.2, width: 0.5, height: 0.6000000000000001,
    });
  });
  it('clamps pointer capture outside the image', () => {
    expect(cropFromPoints([0.2, 0.3], [2, -1])).toEqual({ x: 0.2, y: 0, width: 0.8, height: 0.3 });
  });
});
