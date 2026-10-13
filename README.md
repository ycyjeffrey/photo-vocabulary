# 字拾 · Photo Vocabulary

把英文／繁體中文單字表照片轉成可校正的字卡，再以 TSV 匯入 Quizlet。React + TypeScript 前端、FastAPI 後端、Tesseract 本機 OCR、SQLite 儲存。

**主線功能已實作。真實照片與 Quizlet 帳號內的最終驗收尚待完成。** 專案原本只有 `proposal.md`，沒有提供課本照片或可用的 Quizlet 登入工作階段。內附四種自行產生的控制樣本與自動化測試；它們不能取代真實照片測試。

## 啟動

需求：Python 3.11+、Node.js 22+、npm、curl、Tesseract 5。

macOS 安裝 OCR 引擎：

```bash
brew install tesseract
```

Ubuntu / Debian：

```bash
sudo apt install tesseract-ocr
```

在專案根目錄執行：

```bash
bash scripts/setup.sh
bash scripts/run.sh
```

開啟 **http://127.0.0.1:8000**。保持該終端執行；按 Ctrl+C 停止。

第一次設定會建立 `.venv`、安裝鎖定的依賴、下載英文與繁體中文 OCR 模型，並建置前端。模型來自 Tesseract 官方 `tessdata_best`，固定 revision 並檢查 SHA-256。**安裝需要網路，日常 OCR 不需要網路**；開啟 Quizlet 才會前往外部網站。照片不傳給 Quizlet，也不傳給雲端模型。

## 使用流程

App 與擴充功能右上角都有「深色模式／淺色模式」切換鈕。尚未選擇時跟隨系統外觀；手動選擇後各自記住偏好，重新開啟仍保留。切換不會重設字卡或未儲存的修改，也不會變更 Quizlet 網站本身的外觀。

1. 上傳或拖入一張 JPG / PNG，最多 15 MB、解碼後最多 24 MP。
2. 旋轉照片，拖曳選取單字表範圍；也可用百分比欄位以鍵盤設定裁切。
3. 選擇版面，按「擷取單字」。「自動判斷」找到清楚的英中分隔時，左側用英文模型、右側用繁體中文模型分開辨識，再依同列配對，例如 `dog | 狗` → 單字 `dog`、釋義 `狗`。也可選「左英文｜右中文」強制分開辨識；此模式以裁切後圖片中線分隔，請先裁切到合適位置。「單組單字表」表示一組英中配對；「左右各一組單字表」才是兩組各含英中內容的並排清單。
4. 點字卡或 OCR 區塊，直接在處理後照片上查看來源框。修改錯字、補回漏字、刪除誤擷取。
5. 對照照片，勾選確認。低分、缺少釋義或重新辨識的字卡預設不選取；**所有匯出字卡都必須經使用者確認**。修改內容會取消該卡的確認狀態。
6. 按「驗證並產生 TSV」，複製或下載，再到 Quizlet 建立字卡集的 **Import** 欄位貼上。選 Tab 分隔正反面、換行分隔卡片，設定英文與繁體中文，由使用者最後按 **Create**。

TSV 使用真正的 Tab 與換行，欄位內的 Tab／換行轉為空白。詞性與釋義在背面；原文例句只用於校正與可選的釋義補充，不自動加入匯出。

依據 [Quizlet 官方文字匯入說明](https://help.quizlet.com/hc/en-us/articles/360029977151-Creating-sets-by-importing-content)，文字匯入在網站操作。此專案不依賴 Quizlet API、不收集密碼，也不自動發佈字卡集。

### Chrome 擴充功能（本機載入）

已提供 `extension/` 的 Manifest V3 擴充功能，無需發佈。開啟 `chrome://extensions/` → 開發人員模式 → 載入未封裝項目 → 選本專案的 `extension` 資料夾。

在 app 驗證字卡後，展開「使用 Chrome 擴充功能協助填入 Quizlet」，下載 JSON。到已登入的 Quizlet 建立頁，點擴充功能載入 JSON，再按「填入目前 Quizlet 分頁」。自動偵測失敗可手動開啟 Import，點文字框，再用「填入剛才選取的文字框」。會讀回核對，但不按 Import 確認或 Create。詳見 [擴充功能安裝與操作](extension/README.md)。

已在隔離測試 Chrome 載入擴充功能並驗證表單操作。真實 Quizlet 對測試瀏覽器回傳 403 驗證挑戰，因此登入後網站的最後驗收仍待你在正常 Chrome 操作，不能將合成表單測試當作真實 Quizlet 成功匯入。

## 儲存與隱私

- 原始檔、EXIF 方向校正後預覽、處理後圖片與 SQLite 都在 `data/`。`DATA_DIR` 可覆寫儲存位置。
- 「儲存修改」保留校正進度；成功產生 TSV 時也會儲存。重開頁面後從「本機已儲存」選單恢復。離開未儲存的修改前會提醒。
- 「刪除此照片與辨識資料」會刪除該原始檔、預覽、所有處理版本、快取與相關字卡。正在辨識的照片須等工作結束後才能刪除。
- 沒有自動到期清理；請自行刪除不再需要的照片。硬碟資料未加密，請使用受保護的本機帳號及磁碟。
- 伺服器只綁定 `127.0.0.1`；網頁來源只允許本機 8000 / 5173 連接埠。不要改為對外開放；這不是具備帳號驗證的多人服務。
- `data/`、模型、虛擬環境、依賴及測試輸出均列入 `.gitignore`。

## OCR 與校正策略

1. Pillow 驗證檔案內容、限制像素、修正 EXIF，保留原始檔。
2. 使用者旋轉 → 裁切 → 最長邊縮至 3200 像素。保留轉換資訊；不強制二值化或自動去斜。
3. 自動模式先以 Tesseract `chi_tra+eng`、PSM 6 定位。每組單字表有明確英中分隔時，以 `eng` 重讀英文／詞性區、`chi_tra` 重讀中文區，座標轉回同一張處理後圖片。辨識不到可信分隔時保留混合辨識，使用者可改選「左英文｜右中文」強制左右分開；此模式直接執行兩次單語辨識，不依賴第一次混合辨識成功。標準詞性縮寫統一為小寫，單字拼寫不自動改寫。
4. 自動模式由同列的「英文＋中文 → 第二組英文＋中文」偵測兩組單字表間的分界，至少需要兩列支持。「左右各一組單字表」手動模式以圖片中線分組。每組再各自判斷英中區域；中文欄不是獨立的一組單字。
5. 詞性後若只出現低分非中文文字，對該釋義範圍補做中文 OCR，一次工作最多 20 個範圍。不同讀法保留在 `original_text`，整張卡標為待確認，不默默採信。
6. 各欄獨立分列、配對、合併縮排的換行釋義。低分延續行也會讓整張卡進入待確認。無法配對的內容與未使用的英文區塊列入完整性提醒。
7. 規則足以解析時完全不使用 LLM。來源 ID、英文來源、重複來源、拼寫修改、必填欄位及確認狀態在匯出前再驗證。

所有 `bbox` 為處理後圖片上的 `[x1, y1, x2, y2]`。前端將框與同一張處理圖並排顯示，不混用裁切前座標。

**限制：** 清楚印刷、單頁、單欄或規則雙欄是目標範圍。手寫、嚴重模糊、複雜表格、跨頁、傾斜嚴重、含英文例句的混雜版面可能需要重新裁切或手動修正。自動雙欄失敗時請選雙欄或分別裁切辨識。OCR 可漏字或誤讀標點；例如控制樣本中的全形 `；` 被辨識成半形 `;`，介面保留辨識文字而非假裝知道原文。

## 可選：本機補充詞性與中文釋義

主線不需要模型。若已安裝並執行 Ollama、且已有合適的本機文字模型：

```bash
OLLAMA_MODEL="your-installed-model" bash scripts/run.sh
```

預設連線 `http://127.0.0.1:11434`。`OLLAMA_URL` 只接受本機 HTTP origin，不接受雲端 URL。

此電腦已下載 `qwen3:4b`（約 2.5 GB），並在忽略版本控制的 `.local/ollama-model` 保存模型名稱。`bash scripts/run.sh` 會自動載入；明確設定的 `OLLAMA_MODEL` 環境變數優先。Ollama 需保持執行，重新開機或結束目前工作階段後，可先在另一個終端執行 `ollama serve`，再啟動本專案。沒有設定自動登入啟動服務。

先勾選確認英文單字，再按「補上詞性／中文釋義（本機模型）」。可只補詞性、只補釋義，或兩者都補。模型用現有釋義與例句判斷詞性，採用 `n.`、`v.`、`adj.`、`adv.` 等標準縮寫。

每個欄位分別檢查：只補目前空白、原始辨識也沒有內容的欄位，不覆蓋照片原文或手動修改。即使手動清空照片已有的欄位，也不會改用模型猜填。詞性與釋義各自標示來源；生成欄位標為「模型生成」，整張卡取消選取與確認。沒有上下文的多義詞請特別檢查。服務錯誤、格式錯誤、不完整 ID、無效詞性或非中文釋義都會顯示錯誤。詞性仍是選填欄位，不補也可確認並匯出。

模型 adapter 的契約及失敗情境有模擬測試。短釋義生成會停用模型的 thinking 模式，避免不必要的推理延遲。生成釋義經 OpenCC 轉為臺灣繁體中文；此轉換只用於模型生成內容，不改寫照片原文或手動修改。模型生成仍需逐張確認，不能取代人工對照；這是可選功能，並不阻擋 OCR → 校正 → TSV。

## 架構與 API

```text
frontend/src/     React UI、裁切、來源框、字卡校正與匯出
backend/app.py   HTTP API、單一 worker、工作生命週期
backend/images.py / ocr.py / layout.py
                 圖片限制與轉換、OCR adapter、版面規則
backend/validation.py / model.py
                 匯出驗證、選用本機模型 adapter
backend/store.py SQLite、重啟中斷處理
backend/tests/   API、資料生命週期、配對、模型及實際 OCR 測試
frontend/e2e/    真正瀏覽器的操作測試
extension/       可直接載入的 Chrome MV3 擴充功能、共享 JSON schema
scripts/        設定、啟動、控制樣本產生
```

| Endpoint | 功能 |
|---|---|
| `GET /v1/health` | OCR 準備狀態、模型設定與累計指標 |
| `GET /v1/library` | 已儲存照片及辨識工作索引 |
| `POST /v1/images` | multipart 欄位 `file` 上傳 JPG / PNG |
| `GET /v1/images/{id}/preview` | EXIF 校正後預覽 |
| `POST /v1/extractions` | `{imageId, rotation, crop, layout}` |
| `GET /v1/extractions/{id}` | 工作階段、錯誤、座標及字卡 |
| `GET /v1/extractions/{id}/image` | 座標所對應的處理後圖片 |
| `PUT /v1/extractions/{id}/cards` | 保存校正後字卡；保留原始辨識結果 |
| `POST /v1/cards/enrich` | 補上已確認單字缺少的詞性／中文釋義 |
| `POST /v1/cards/validate` | 回傳 issues、valid、selectedCount、TSV |
| `DELETE /v1/images/{id}` | 刪除照片及所有相關資料 |

`crop` 為旋轉後圖片的 `{x, y, width, height}`，各值以 0–1 表示。`rotation` 為順時針 0 / 90 / 180 / 270 度。卡片相關 request 為 `{extractionId, cards}`。完整 schema 見 http://127.0.0.1:8000/docs。

工作階段：`queued → preprocessing → recognizing → structuring → completed / failed`。一個程序、一個執行緒 worker，同時最多 8 個未完成辨識工作；模型呼叫也使用該 worker。不使用 Redis 或 Celery，**不要用多個 Uvicorn worker**。重啟時未完成辨識標為中斷，使用者可重跑。

快取鍵包含圖片像素雜湊、旋轉、裁切、版面、pipeline 版本與本機模型檔案簽章。相同內容的不同上傳可重用 OCR 結果，但各自保有處理圖，刪除其中一張不會破壞另一張；校正修改不會污染快取原稿。

OCR 次數計算**實際 Tesseract 呼叫**，不是按鈕次數：單欄通常 1 次；手動雙欄通常 2 次；自動雙欄包含偵測用全圖辨識，因此通常 3 次；釋義重查另計。快取不呼叫 OCR。模型計數包含呼叫嘗試，失敗也計入。耗時是工作開始後的處理時間，不含排隊；沒有測量耗電，不宣稱省電百分比。

## 開發與驗證

前端開發伺服器（另一個終端，後端仍以 `bash scripts/run.sh` 執行）：

```bash
npm --prefix frontend run dev
```

開啟 http://127.0.0.1:5173；Vite 將 `/v1` 代理至後端。

一般測試與建置：

```bash
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run build
```

產生四張**控制樣本，不是真實課本照片**，並測試實際 OCR：

```bash
.venv/bin/python scripts/generate_demo.py
RUN_OCR_TESTS=1 .venv/bin/python -m pytest backend/tests -q
```

產物在 `.local/demo/`：`single.png`、`double.png`、`wrapped.png`、`expected.json`。需要本機中文字型；macOS 使用系統黑體，Linux 尋找 Noto CJK。找不到時：

```bash
.venv/bin/python scripts/generate_demo.py --font /path/to/chinese-font.ttc
DEMO_FONT=/path/to/chinese-font.ttc RUN_OCR_TESTS=1 .venv/bin/python -m pytest backend/tests -q
```

原有三張樣本的實際 OCR 測試逐張比較完整單字、詞性、中文及欄列配對，只忽略全形／半形分號差異。新增英中分欄樣本驗證英文／中文模型各自被呼叫，並精確核對 `dog → 狗`、`cat → 貓`，涵蓋單列與多列。此字型的單字元 `鳥` 可能被辨識為 `島`，測試要求誤讀時必須標記待確認且不選取，不用英文單字猜測或替換原文。另驗證缺釋義卡預設排除。四張控制樣本共 15 張字卡，14 張有釋義、1 張刻意留空。

瀏覽器測試（先產生控制樣本並啟動 http://127.0.0.1:8000）：

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

涵蓋上傳、實際 OCR、來源框、確認攔截、修正後取消確認、複製及下載 TSV、儲存後重載、照片刪除、旋轉／裁切、快取、換行釋義、待確認預設排除、手動新增與刪卡、桌面／手機寬度。測試只清理自己建立的照片；截圖在 `frontend/test-results/`。

已啟動並設定本機模型時，可額外執行 `RUN_MODEL_TESTS=1 npm run test:e2e`。這會透過真實模型與瀏覽器驗證只補詞性、只補釋義、兩者都補、逐欄來源標示、保留原文／手動內容、重新確認、TSV 與保存後重載。

## 尚待完成的真實驗收

以下不是已通過的測試，需具備真實照片與登入 Quizlet 的使用者操作：

1. 三張不同的實際單字表照片：單欄、雙欄、換行釋義或模糊單字。手工建立對照答案，逐字檢查漏字、錯配、標題／例句誤收及待確認標記。
2. 使用 app 完成來源定位與校正。複製 TSV 到已登入的 Quizlet，選語言，建立字卡集。
3. 逐張核對 Quizlet 中的卡片數、正反面文字，至少翻看數張；完成 proposal 所定義的三分鐘 demo。

Chrome extension 加分路徑已實作，使用下載 JSON 交接，不建立持續連線或自動發佈。人工 TSV 匯入仍可獨立使用。未驗證的 OCR/模型結果不應被當作可靠原文。

## 本機版本控制

`main` 保存擴充功能開發前的 app baseline（`55051d3`）。擴充功能於 `feat/quizlet-chrome-extension` 分支開發與提交，驗收後可用一般 merge 合併；不覆寫既有提交。尚未設定遠端或推送到 GitHub。照片、模型、環境與本機設定不納入版本控制。
