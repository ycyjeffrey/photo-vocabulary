import { useEffect, useState } from 'react';
import { api, download, jsonRequest } from './api';
import { canEnrich } from './enrichment';
import { createQuizletPacket } from './quizlet';
import { PhotoPanel } from './PhotoPanel';
import type { Card, Crop, Extraction, Health, Library, Photo, Validation } from './types';

const stages: Record<Extraction['status'], string> = {
  queued: '排隊中', preprocessing: '處理照片', recognizing: '辨識中英文',
  structuring: '配對單字與釋義', completed: '擷取完成', failed: '辨識失敗',
};
const originNames = { photo: '照片原文', model: '模型生成', manual: '手動編輯', missing: '缺少釋義' };
const message = (error: unknown) => error instanceof Error ? error.message : String(error);

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [library, setLibrary] = useState<Library>({ images: [], extractions: [] });
  const [photo, setPhoto] = useState<Photo | null>(null);
  const [rotation, setRotation] = useState<0 | 90 | 180 | 270>(0);
  const [crop, setCrop] = useState<Crop | null>(null);
  const [layout, setLayout] = useState<'auto' | 'single' | 'double'>('auto');
  const [job, setJob] = useState<Extraction | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [activeCard, setActiveCard] = useState('');
  const [extraHighlight, setExtraHighlight] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [reviewOnly, setReviewOnly] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [setTitle, setSetTitle] = useState('我的單字集');
  const [pollStopped, setPollStopped] = useState(false);
  const processing = !!job && !['completed', 'failed'].includes(job.status);
  const locked = busy || processing;
  const complete = job?.status === 'completed';

  const refresh = async () => {
    const [nextHealth, nextLibrary] = await Promise.all([
      api<Health>('/v1/health'), api<Library>('/v1/library'),
    ]);
    setHealth(nextHealth);
    setLibrary(nextLibrary);
  };
  useEffect(() => {
    void refresh().catch(error => setError(message(error)));
  }, []);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  useEffect(() => {
    if (!job || !processing || pollStopped) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await api<Extraction>(`/v1/extractions/${job.id}`);
        if (cancelled) return;
        setJob(result);
        if (result.status === 'completed') {
          setCards(result.reviewed_cards ?? result.draft_cards);
          setActiveCard((result.reviewed_cards ?? result.draft_cards)[0]?.id ?? '');
          setDirty(false);
          await refresh();
        } else if (result.status === 'failed') {
          setError(result.error ?? '辨識失敗，請重試。');
          await refresh();
        } else {
          timer = setTimeout(() => void poll(), 700);
        }
      } catch (error) {
        if (!cancelled) {
          setError(`無法取得工作狀態：${message(error)}`);
          setPollStopped(true);
        }
      }
    };
    timer = setTimeout(() => void poll(), 350);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [job?.id, processing, pollStopped]);

  const safeToReplace = () => !dirty || window.confirm('有尚未儲存的修改，確定放棄嗎？');
  const run = async (operation: () => Promise<void>) => {
    setBusy(true);
    setError('');
    setNotice('');
    try { await operation(); } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  };
  const resetReview = () => {
    setJob(null); setCards([]); setActiveCard(''); setValidation(null);
    setExtraHighlight([]); setShowOriginal(false); setDirty(false); setPollStopped(false);
  };
  const upload = (file: File | undefined) => {
    if (!file || locked || !safeToReplace()) return;
    if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 15 * 1024 * 1024) {
      setError('請選擇 15 MB 以下的 JPG 或 PNG 照片。');
      return;
    }
    void run(async () => {
      const body = new FormData();
      body.append('file', file);
      const result = await api<Photo>('/v1/images', { method: 'POST', body });
      resetReview(); setPhoto(result); setRotation(0); setCrop(null); setLayout('auto');
      await refresh();
    });
  };
  const loadPhoto = (imageId: string) => {
    if (locked || !safeToReplace()) return;
    const saved = library.images.find(image => image.id === imageId);
    if (!saved) return;
    void run(async () => {
      const latest = library.extractions.find(item => item.imageId === imageId);
      const result = latest ? await api<Extraction>(`/v1/extractions/${latest.id}`) : null;
      resetReview();
      setPhoto({ ...saved, imageId: saved.id });
      setRotation(result?.settings.rotation ?? 0);
      setCrop(result?.settings.crop ?? null);
      setLayout(result?.settings.layout ?? 'auto');
      if (result) {
        setJob(result);
        setCards(result.reviewed_cards ?? result.draft_cards);
        setActiveCard((result.reviewed_cards ?? result.draft_cards)[0]?.id ?? '');
      }
    });
  };
  const extract = () => {
    if (!photo || !safeToReplace()) return;
    void run(async () => {
      const result = await api<Extraction>('/v1/extractions', jsonRequest('POST', {
        imageId: photo.imageId, rotation, crop, layout,
      }));
      resetReview(); setJob(result);
      if (result.status === 'completed') {
        setCards(result.draft_cards); setActiveCard(result.draft_cards[0]?.id ?? '');
        await refresh();
      }
    });
  };
  const editCard = (id: string, update: Partial<Card>, contentEdit = false) => {
    setCards(current => current.map(card => card.id === id ? {
      ...card, ...update, ...(contentEdit ? { confirmed: false } : {}),
    } : card));
    setDirty(true); setValidation(null); setNotice('');
  };
  const save = async () => {
    if (!job) return;
    await api(`/v1/extractions/${job.id}/cards`, jsonRequest('PUT', { extractionId: job.id, cards }));
    setDirty(false);
  };
  const exportCards = () => {
    if (!job) return;
    void run(async () => {
      const result = await api<Validation>('/v1/cards/validate',
        jsonRequest('POST', { extractionId: job.id, cards }));
      setValidation(result);
      if (!result.valid) {
        throw new Error('請至少選取一張字卡，填妥單字與釋義，並確認所有選取字卡。');
      }
      await save();
      setNotice(`已準備 ${result.selectedCount} 張字卡。複製下方 TSV，貼到 Quizlet 匯入頁。`);
    });
  };
  const selectedCount = cards.filter(c => c.selected).length;
  const reviewCount = cards.filter(c => !c.confirmed && (c.needs_review || !c.definition)).length;
  const highlighted = extraHighlight.length ? extraHighlight
    : cards.find(c => c.id === activeCard)?.source_block_ids ?? [];

  return (
    <div className="app">
      <header>
        <a href="/" className="brand"><span className="brand-icon">字</span>字拾 <span>Photo Vocabulary</span></a>
        <span className="local-badge"><span className="dot" /> 本機處理 · 照片不外傳</span>
      </header>
      <main>
        <div className="intro">
          <div><p className="eyebrow">FROM YOUR PAGE TO YOUR NEXT PRACTICE</p>
            <h1>拍下單字，留下所學。</h1>
            <p>擷取課本單字表，對照照片確認，帶進 Quizlet 開始練習。</p></div>
          <div className="steps"><span className={!photo ? 'current' : ''}>1 上傳照片</span><i>→</i>
            <span className={photo && !validation?.valid ? 'current' : ''}>2 對照確認</span><i>→</i>
            <span className={validation?.valid ? 'current' : ''}>3 匯入字卡</span></div>
        </div>

        {error && <div className="banner error" role="alert">{error}<button onClick={() => setError('')}>關閉</button></div>}
        {notice && <div className="banner success" role="status">{notice}</div>}
        {health && !health.ocrReady && <div className="banner warning" role="alert">{health.ocrMessage}</div>}

        <section className="workspace">
          <aside className="left-column">
            <section className="surface upload-card" onDragOver={event => event.preventDefault()}
              onDrop={event => {
                event.preventDefault();
                if (event.dataTransfer.files.length !== 1) setError('一次請只上傳一張照片。');
                else upload(event.dataTransfer.files[0]);
              }}>
              <div className="section-title"><h2>你的單字照片</h2><span className="tag">JPG / PNG</span></div>
              <label className={`upload-zone ${locked ? 'disabled' : ''}`}>
                <span className="upload-icon">＋</span>
                <strong>{photo ? '選擇另一張照片' : '拖曳照片到這裡，或點擊上傳'}</strong>
                <span>清楚印刷 · 英文／繁體中文 · 上限 15 MB / 24 MP</span>
                <input aria-label="上傳單字表照片" type="file" accept="image/jpeg,image/png" disabled={locked}
                  onChange={event => { upload(event.target.files?.[0]); event.target.value = ''; }} />
              </label>
              {library.images.length > 0 && <label className="library-label">本機已儲存
                <select aria-label="開啟已儲存照片" value={photo?.imageId ?? ''} disabled={locked}
                  onChange={event => loadPhoto(event.target.value)}>
                  <option value="">選擇照片</option>
                  {library.images.map(image => <option key={image.id} value={image.id}>
                    {image.id.slice(0, 8)} · {image.width} × {image.height}
                  </option>)}
                </select>
              </label>}
            </section>

            {photo && <section className="surface">
              <div className="toolbar">
                <button disabled={locked} onClick={() => {
                  setRotation(value => ((value + 90) % 360) as 0 | 90 | 180 | 270);
                  setCrop(null); setShowOriginal(true);
                }}>↻ 旋轉 90°</button>
                <button disabled={locked || !crop} onClick={() => { setCrop(null); setShowOriginal(true); }}>清除裁切</button>
                {complete && <button disabled={locked} onClick={() => setShowOriginal(value => !value)}>
                  {showOriginal ? '回到來源定位' : '重新裁切'}
                </button>}
              </div>
              <PhotoPanel photo={photo} rotation={rotation} crop={crop}
                onCrop={setCrop} disabled={locked}
                processedUrl={complete && !showOriginal ? job.processedUrl : undefined}
                processedSize={job?.transform?.processedSize} blocks={job?.ocr_blocks ?? []} highlighted={highlighted} />
              <fieldset className="crop-inputs" disabled={locked}>
                <legend>裁切範圍（%，可鍵盤調整）</legend>
                {(['x', 'y', 'width', 'height'] as const).map((key, index) => (
                  <label key={key}>{['左', '上', '寬', '高'][index]}
                    <input type="number" min={key === 'width' || key === 'height' ? 1 : 0} max="100"
                      aria-label={`裁切${['左', '上', '寬', '高'][index]}`}
                      value={Math.round((crop ?? { x: 0, y: 0, width: 1, height: 1 })[key] * 100)}
                      onChange={event => {
                        const next = { ...(crop ?? { x: 0, y: 0, width: 1, height: 1 }),
                          [key]: Math.max(0, Math.min(1, Number(event.target.value) / 100)) };
                        next.x = Math.min(next.x, 0.99); next.y = Math.min(next.y, 0.99);
                        next.width = Math.max(0.01, Math.min(next.width, 1 - next.x));
                        next.height = Math.max(0.01, Math.min(next.height, 1 - next.y));
                        setCrop(next); setShowOriginal(true);
                      }} />
                  </label>
                ))}
              </fieldset>
              <div className="extraction-controls">
                <label>版面 <select value={layout} disabled={locked}
                  onChange={event => setLayout(event.target.value as typeof layout)}>
                  <option value="auto">自動判斷</option><option value="single">單欄</option><option value="double">雙欄</option>
                </select></label>
                <button className="primary" onClick={extract} disabled={locked || !health?.ocrReady}>
                  {processing ? stages[job.status] + '…' : '擷取單字'}
                </button>
              </div>
              {processing && <div role="status" className="progress"><span />{stages[job.status]}，請稍候。
                {pollStopped && <button onClick={() => { setPollStopped(false); setError(''); }}>重新連線</button>}
              </div>}
              <button className="danger text-button" disabled={locked} onClick={() => {
                if (!window.confirm('刪除此照片、原始檔與所有相關辨識結果？此動作無法復原。')) return;
                void run(async () => {
                  await api(`/v1/images/${photo.imageId}`, { method: 'DELETE' });
                  resetReview(); setPhoto(null); await refresh(); setNotice('照片與相關辨識資料已從本機刪除。');
                });
              }}>刪除此照片與辨識資料</button>
            </section>}
            <div className="privacy-note"><strong>只在你按下辨識時運作。</strong>
              <p>規則能配對就不使用模型；相同設定使用快取。不持續監控相機，不收集 Quizlet 帳密。</p></div>
          </aside>

          <section className="surface cards-panel">
            <div className="section-title"><div><p className="eyebrow">REVIEW BEFORE YOU REMEMBER</p><h2>對照你的字卡</h2></div>
              {complete && <span className="tag">{cards.length} 張</span>}</div>
            {!complete ? <div className="empty-state"><div className="empty-cards"><span>Aa</span><span>字</span></div>
              <h3>{processing ? '正在讀取你的單字表' : '把照片變成可練習的字卡'}</h3>
              <p>辨識後，單字與原文位置會一起出現。<br />先確認，再匯入；不確定的內容不會自動選取。</p></div> : <>
              <div className="review-summary"><span><strong>{selectedCount}</strong> 已選取</span>
                <span className={reviewCount ? 'warning-text' : ''}><strong>{reviewCount}</strong> 待確認</span>
                <label><input type="checkbox" checked={reviewOnly} onChange={event => setReviewOnly(event.target.checked)} />只看待確認</label>
              </div>
              <div className="card-actions">
                <button disabled={busy} onClick={() => {
                  const newCard: Card = {
                    id: crypto.randomUUID(), term: '', part_of_speech: '', definition: '', example: '',
                    source_block_ids: [], definitionOrigin: 'manual', partOfSpeechOrigin: 'manual', needs_review: true,
                    review_reason: '手動新增，請對照照片', selected: false, confirmed: false,
                  };
                  setCards(current => [...current, newCard]); setActiveCard(newCard.id);
                  setExtraHighlight([]); setDirty(true); setValidation(null);
                }}>＋ 新增漏掉的單字</button>
                <button disabled={busy || !dirty} onClick={() => void run(async () => { await save(); setNotice('修改已儲存在本機。'); })}>
                  {dirty ? '儲存修改' : '已儲存'}
                </button>
                <button disabled={busy || !health?.modelConfigured ||
                  !cards.some(c => canEnrich(c, job.draft_cards.find(original => original.id === c.id)))}
                  title={health?.modelConfigured ? '僅補充已確認單字的空白詞性與釋義，不覆蓋既有內容' : health?.modelMessage}
                  onClick={() => void run(async () => {
                    const result = await api<{ cards: Card[] }>('/v1/cards/enrich',
                      jsonRequest('POST', { extractionId: job.id, cards }));
                    setCards(result.cards); setDirty(true); setValidation(null); await refresh();
                    setNotice('已補上缺少的詞性／中文釋義；生成內容請逐張確認後再選取。');
                  })}>補上詞性／中文釋義（本機模型）</button>
              </div>
              <fieldset className="card-list" disabled={busy}>
                <legend className="sr-only">編輯與確認字卡</legend>
                {cards.filter(c => !reviewOnly || (!c.confirmed && (c.needs_review || !c.definition))).map(card => (
                  <article key={card.id} className={`vocab-card ${activeCard === card.id && !extraHighlight.length ? 'active' : ''}`}
                    onClick={() => { setActiveCard(card.id); setExtraHighlight([]); setShowOriginal(false); }}
                    onFocus={() => { setActiveCard(card.id); setExtraHighlight([]); }}>
                    <div className="card-top">
                      <label className="select-card"><input type="checkbox" aria-label={`選取 ${card.term || '新單字'}`}
                        checked={card.selected} disabled={card.needs_review && !card.confirmed}
                        onChange={event => editCard(card.id, { selected: event.target.checked })} />匯出</label>
                      <button className="source-link" title="在照片上框出來源" onClick={() => {
                        setActiveCard(card.id); setExtraHighlight([]); setShowOriginal(false);
                      }}>{card.source_block_ids.length ? '⌖ 查看來源' : '手動新增'}</button>
                      <span className={`status-tag ${card.confirmed ? 'confirmed' : card.needs_review ? 'review-needed' : ''}`}>
                        {card.confirmed ? '已確認' : card.needs_review ? '待確認' : '已擷取'}
                      </span>
                      <button className="delete-card" aria-label={`刪除 ${card.term || '新單字'}`} onClick={event => {
                        event.stopPropagation(); setCards(current => current.filter(c => c.id !== card.id));
                        setDirty(true); setValidation(null);
                      }}>×</button>
                    </div>
                    <div className="card-fields">
                      <label>單字／片語<input aria-label={`單字 ${card.id}`} value={card.term} maxLength={300}
                        onChange={event => editCard(card.id, { term: event.target.value }, true)} /></label>
                      <label className="pos-field">詞性<input aria-label={`詞性 ${card.id}`} value={card.part_of_speech} maxLength={100}
                        onChange={event => editCard(card.id, {
                          part_of_speech: event.target.value, partOfSpeechOrigin: 'manual',
                        }, true)} />
                        {card.part_of_speech && <span className={`pos-origin ${card.partOfSpeechOrigin ?? 'photo'}`}>
                          {originNames[card.partOfSpeechOrigin ?? 'photo']}
                        </span>}
                      </label>
                      <label className="definition-field">中文釋義 <span className={`origin ${card.definitionOrigin}`}>{originNames[card.definitionOrigin]}</span>
                        <textarea aria-label={`釋義 ${card.id}`} rows={2} value={card.definition} maxLength={3000}
                          onChange={event => editCard(card.id, { definition: event.target.value, definitionOrigin: 'manual' }, true)} /></label>
                    </div>
                    {card.example && <p className="example">原文例句：{card.example}</p>}
                    {job.draft_cards.some(original => original.id === card.id && original.term !== card.term) &&
                      <p className="review-reason">拼寫已修改；原擷取內容：{job.draft_cards.find(original => original.id === card.id)?.term}</p>}
                    {card.review_reason && !card.confirmed && <p className="review-reason">{card.review_reason}</p>}
                    <label className="confirm-card"><input type="checkbox" checked={card.confirmed}
                      aria-label={`確認 ${card.term || '新單字'}`}
                      onChange={event => editCard(card.id, {
                        confirmed: event.target.checked,
                        selected: event.target.checked && !!card.definition.trim(),
                      })} />{card.definition && card.part_of_speech ? '我已對照照片，確認單字、詞性與釋義'
                        : '我已確認英文單字與現有內容（可補上空白詞性／釋義）'}</label>
                  </article>
                ))}
              </fieldset>
              {cards.length === 0 && <p className="muted">尚未找到字卡。請重新裁切、調整版面，或手動新增。</p>}
              {job.warnings.length > 0 && <details className="warnings"><summary>來源完整性提醒（{job.warnings.length}）</summary>
                {job.warnings.map((warning, i) => <p key={i}>{warning}</p>)}</details>}
              <details className="ocr-details"><summary>查看 OCR 區塊與辨識分數（{job.ocr_blocks.length}）</summary>
                <div className="block-list">{job.ocr_blocks.map(block => <button key={block.id}
                  onClick={() => { setExtraHighlight([block.id]); setShowOriginal(false); }}>
                  {block.id} · {block.text} <span>{Math.round(block.ocr_score * 100)}%</span>
                  {block.original_text && <span>重新辨識前：{block.original_text}</span>}
                </button>)}</div>
              </details>
              <div className="export-bar">
                <button disabled={busy || !selectedCount} onClick={() => {
                  setCards(current => current.map(c => c.selected ? { ...c, confirmed: true } : c));
                  setDirty(true); setValidation(null);
                }}>我已核對，確認已選字卡</button>
                <button className="primary" disabled={busy || !selectedCount} onClick={exportCards}>驗證並產生 TSV →</button>
              </div>
              {validation && <section className="export-result">
                {validation.missedBlockIds.length > 0 && <details className="warnings">
                  <summary>未使用的英文來源（{validation.missedBlockIds.length}）：可能是刪除的卡片或漏擷取</summary>
                  <div className="block-list">{validation.missedBlockIds.map(id => <button key={id}
                    onClick={() => { setExtraHighlight([id]); setShowOriginal(false); }}>
                    {id} · {job.ocr_blocks.find(block => block.id === id)?.text}
                  </button>)}</div>
                </details>}
                {validation.issues.filter(issue => issue.blocking || issue.warnings.length).map((issue, i) =>
                  <p className={issue.blocking ? 'error-text' : 'muted'} key={i}>
                    {cards.find(c => c.id === issue.cardId)?.term}: {[...issue.errors, ...issue.warnings].join('；')}
                  </p>)}
                {validation.valid && <>
                  <h3>帶進 Quizlet，開始練習</h3>
                  <p>複製文字 → 開啟 Quizlet 建立頁的「匯入」→ 貼上。選擇 Tab 分隔正反面、換行分隔字卡，
                    設定英文與繁體中文後，由你按下 Create。</p>
                  <textarea readOnly aria-label="Quizlet TSV" rows={6} value={validation.tsv} />
                  <div className="toolbar">
                    <button className="primary" onClick={() => void run(async () => {
                      await navigator.clipboard.writeText(validation.tsv);
                      setNotice(`已複製 ${validation.selectedCount} 張字卡。`);
                    })}>複製 TSV</button>
                    <button onClick={() => download(validation.tsv, 'vocabulary.tsv', 'text/tab-separated-values;charset=utf-8')}>下載 TSV</button>
                    <a className="button" href="https://quizlet.com/create-set" target="_blank" rel="noreferrer">開啟 Quizlet ↗</a>
                  </div>
                  <p className="muted">只匯入你確認的文字，不傳送照片。建立前請核對卡片數：{validation.selectedCount}。</p>
                  <details className="extension-export">
                    <summary>使用 Chrome 擴充功能協助填入 Quizlet</summary>
                    <p>先在 chrome://extensions 開啟開發人員模式，載入本專案的 extension 資料夾。
                      下載下方 JSON，切到 Quizlet 建立頁，點擴充功能載入並填入。Import 與 Create 仍由你操作。</p>
                    <label>字卡集標題<input aria-label="字卡集標題" value={setTitle} maxLength={200}
                      onChange={event => setSetTitle(event.target.value)} /></label>
                    <button disabled={busy} onClick={() => void run(async () => {
                      const packet = createQuizletPacket(validation, setTitle);
                      download(JSON.stringify(packet, null, 2), 'quizlet-cards.json', 'application/json;charset=utf-8');
                      setNotice(`已下載 ${packet.cards.length} 張已確認字卡，請在 Chrome 擴充功能載入 JSON。`);
                    })}>下載擴充功能 JSON</button>
                  </details>
                </>}
              </section>}
            </>}
          </section>
        </section>
        <footer>
          <span>字拾 · Local-first vocabulary studio</span>
          <div className="metrics"><span>OCR <b>{health?.metrics.ocrCalls ?? 0}</b> 次</span>
            <span>模型 <b>{health?.metrics.modelCalls ?? 0}</b> 次</span><span>快取 <b>{health?.metrics.cacheHits ?? 0}</b> 次</span>
            {complete && <span>{job.cacheHit ? '本次命中快取' : `本次 ${(job.elapsedMs / 1000).toFixed(1)} 秒`}</span>}</div>
        </footer>
      </main>
    </div>
  );
}
