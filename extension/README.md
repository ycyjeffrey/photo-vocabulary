# 字拾 · Quizlet Import Helper

本機安裝的 Chrome Manifest V3 擴充功能。不需要發佈 Chrome Web Store，也不需要 Quizlet API 或密碼。

## 安裝到你的 Chrome

1. 開啟 `chrome://extensions/`。
2. 右上角打開 **Developer mode／開發人員模式**。
3. 按 **Load unpacked／載入未封裝項目**，選擇：

   ```text
   /Users/chengyun/Desktop/CN_hackthon/extension
   ```

4. 在 Chrome 工具列的拼圖選單，釘選 **字拾 · Quizlet Import Helper**。

擴充功能無需編譯，載入此資料夾即可。更新程式碼後，在 `chrome://extensions/` 的擴充功能卡片按重新載入，再關閉並重開 popup。不要選整個專案資料夾。

## 從照片到 Quizlet

1. 開啟本機 app：<http://127.0.0.1:8000>。對照照片，修正並確認要匯出的字卡。
2. 按 **驗證並產生 TSV**，展開 **使用 Chrome 擴充功能協助填入 Quizlet**。
3. 填字卡集標題，按 **下載擴充功能 JSON**。檔名是 `quizlet-cards.json`，只包含已確認、已選取字卡的文字，沒有照片、來源座標或帳號資料。
4. 在正常 Chrome 分頁登入 Quizlet，開啟 <https://quizlet.com/create-set>。如果 Quizlet 顯示驗證挑戰，請在你自己的瀏覽器正常完成；擴充功能不會繞過驗證。
5. 點字拾擴充功能，載入 JSON，確認張數及標題，按 **填入目前 Quizlet 分頁**。保持面板開啟，等待讀回核對結果。
6. 自動偵測失敗時，在 Quizlet 手動開啟 **Import**，點一下貼上文字的大文字框，再開啟擴充功能，按 **填入剛才選取的文字框**。
7. 在 Quizlet 選擇 **Tab** 分隔正反面、**換行**分隔字卡，核對預覽張數。**自行按 Import**，設定英文／繁體中文，核對完成後**自行按 Create**。

擴充功能只開啟 Import 入口、填文字並讀回；**不會按 Import 確認或 Create，不會自動發佈**。如果 import dialog 遮住或移除了標題欄位，訊息會提醒你手動填標題。若有既存標題或匯入文字，預設不覆寫；要取代時必須明確勾選允許取代。

備援：展開面板中的手動貼上區域，按 **複製 TSV**，直接貼入 Quizlet。若 clipboard 權限被瀏覽器禁止，也可以在文字框內自行全選複製。不要把 TSV 貼進單張卡片的正面或背面。

## 權限與資料

- `activeTab`：只有你啟動擴充功能時，才取得目前分頁的暫時權限。
- `scripting`：將填寫函式注入目前 Quizlet 建立頁，執行於隔離的 content-script world。
- `storage`：把載入字卡保留於此 Chrome profile 的本機儲存空間；不使用同步儲存。
- `clipboardWrite`：你按「複製 TSV」時寫入剪貼簿。

沒有全網站或持續性的 host permissions，沒有背景網頁監控、遠端 JavaScript、帳密讀取、照片上傳、Quizlet API 呼叫或自動 Create。沒有網站可呼叫的 external message 通道。只有 HTTPS `quizlet.com` / `www.quizlet.com` 的 `/create-set`（含語系前綴）可執行填入。

載入字卡會在本機持續保存，未加密；使用完可按 **清除擴充功能中的字卡**。這不刪除本機 app 的資料或 Quizlet 上的字卡集。新 JSON 驗證失敗時會清掉舊的待匯入資料，避免誤填上一份。JSON 檔案最多 2 MB、500 張；不接受未確認卡片。

## 驗證範圍與實際限制

已測試 MV3 實際載入、popup 載入 JSON／保存／清除、Chrome `activeTab` 授權後真正的 `chrome.scripting.executeScript` 隔離世界注入、標題與 TSV 填入、原生 input/change 事件、讀回、覆寫保護、焦點備援、拒絕其他頁面以及「不按 Import/Create」。

**測試頁是合成的匯入表單，不是真實 Quizlet 登入後 DOM。** 嘗試存取真實 Quizlet 建立頁時，測試瀏覽器收到 HTTP 403 驗證挑戰；沒有繞過挑戰，也沒有存取你的私人 Chrome profile。故尚未聲稱「已在你的登入帳號成功建立字卡集」。請依上述流程在你的 Chrome 做最後驗收。若網站改版，優先使用焦點文字框模式或複製 TSV；未知或多個候選欄位會顯示錯誤，不亂猜。

控制台測試：

```bash
# 從專案根目錄
npm --prefix extension test
npm --prefix frontend run test:e2e -- e2e/extension.spec.ts
```

瀏覽器測試使用全新暫存 profile，不讀取、改動你的日常 Chrome profile。測試中的 `--enable-unsafe-extension-debugging` 只用於啟動合成頁面的測試瀏覽器，**正常安裝不需要也不應加入此旗標**。

主程式的「下載 JSON」與 TSV 等價性另有前端單元測試與 app 的端對端測試。JSON schema 固定 `format: "photo-vocabulary.quizlet"`、`version: 1`，每張卡包含 `term`、`definition`（詞性＋釋義）與 `confirmed: true`。
