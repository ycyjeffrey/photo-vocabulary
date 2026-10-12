import { useEffect, useRef, useState } from 'react';
import { cropFromPoints } from './geometry';
import type { Block, Crop, Photo } from './types';

type Props = {
  photo: Photo; rotation: number; crop: Crop | null;
  onCrop: (crop: Crop | null) => void;
  processedUrl?: string; processedSize?: [number, number];
  blocks: Block[]; highlighted: string[]; disabled: boolean;
};

export function PhotoPanel(props: Props) {
  const { photo, rotation, crop, onCrop, processedUrl, processedSize, blocks, highlighted, disabled } = props;
  const canvas = useRef<HTMLCanvasElement>(null);
  const start = useRef<[number, number] | null>(null);
  const [loadError, setLoadError] = useState('');
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setReady(false);
    setLoadError('');
    const image = new Image();
    image.onload = () => {
      if (cancelled || !canvas.current) return;
      const target = canvas.current;
      const sideways = !processedUrl && rotation % 180 !== 0;
      target.width = sideways ? image.height : image.width;
      target.height = sideways ? image.width : image.height;
      const context = target.getContext('2d');
      if (!context) {
        setLoadError('無法建立圖片預覽。');
        return;
      }
      context.translate(target.width / 2, target.height / 2);
      context.rotate((processedUrl ? 0 : rotation) * Math.PI / 180);
      context.drawImage(image, -image.width / 2, -image.height / 2);
      setReady(true);
    };
    image.onerror = () => { if (!cancelled) setLoadError('圖片載入失敗，請重新開啟照片。'); };
    image.src = processedUrl || photo.previewUrl;
    return () => { cancelled = true; };
  }, [photo.previewUrl, rotation, processedUrl]);

  const point = (event: React.PointerEvent<HTMLDivElement>): [number, number] => {
    const rect = event.currentTarget.getBoundingClientRect();
    return [(event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height];
  };
  return (
    <div className="photo-panel">
      <div className="panel-heading">
        <span>{processedUrl ? '來源定位' : '照片範圍'}</span>
        <span className="muted">{processedUrl ? '點擊字卡，查看原文位置' : '在照片上拖曳以裁切'}</span>
      </div>
      {loadError && <p role="alert">{loadError}</p>}
      <div className={`photo-stage ${processedUrl ? 'review' : 'crop'}`}
        onPointerDown={event => {
          if (processedUrl || disabled || !ready) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          start.current = point(event);
          onCrop(null);
        }}
        onPointerMove={event => {
          if (start.current) onCrop(cropFromPoints(start.current, point(event)));
        }}
        onPointerUp={event => {
          if (!start.current) return;
          const next = cropFromPoints(start.current, point(event));
          onCrop(next.width > 0.01 && next.height > 0.01 ? next : null);
          start.current = null;
        }}
        onPointerCancel={() => { start.current = null; onCrop(null); }}
        aria-label={processedUrl ? '已處理照片與來源框' : '拖曳裁切照片'}>
        <canvas ref={canvas} />
        {!processedUrl && crop && <div className="crop-box" style={{
          left: `${crop.x * 100}%`, top: `${crop.y * 100}%`,
          width: `${crop.width * 100}%`, height: `${crop.height * 100}%`,
        }} />}
        {processedUrl && processedSize && blocks.filter(b => highlighted.includes(b.id)).map(block => (
          <div key={block.id} className="source-box" title={`${block.text} · OCR ${Math.round(block.ocr_score * 100)}%`}
            style={{
              left: `${block.bbox[0] / processedSize[0] * 100}%`,
              top: `${block.bbox[1] / processedSize[1] * 100}%`,
              width: `${(block.bbox[2] - block.bbox[0]) / processedSize[0] * 100}%`,
              height: `${(block.bbox[3] - block.bbox[1]) / processedSize[1] * 100}%`,
            }} />
        ))}
      </div>
      <p className="muted photo-caption">
        {processedUrl ? '座標對應處理後圖片。OCR 分數僅供檢查排序，不代表字卡正確率。' : '保留原始照片；旋轉後再選取裁切範圍。一次處理一張照片。'}
      </p>
    </div>
  );
}
