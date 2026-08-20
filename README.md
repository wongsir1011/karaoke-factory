# K 歌工房

一個只在本機運行嘅 Streamlit 工具，可以將 YouTube MV 或本機影片製作成卡拉 OK MP4：

- 下載單一 YouTube 影片，最高 1080p，支援 EJS 挑戰解算、斷點續傳同漸進重試
- 用 Demucs AI 分離主唱，或用 FFmpeg 快速消除中心聲道
- 處理影片前先確認歌詞：優先搜尋 Kugeci，搵唔到先使用後備同步歌詞服務
- 亦可自行上載 LRC，或者貼上普通逐行歌詞，讓 AI 聽歌後產生句級時間
- AI 對時會先用 Demucs 抽出主唱，再用 Whisper 辨認位置；完成後可播放原曲逐句校正及匯出 LRC
- 無論來源係簡體、繁體或混合中文，字幕一律轉成香港繁體
- 產生雙行預覽、逐字／逐詞變色嘅卡拉 OK 字幕
- 將無人聲音軌同字幕直接燒錄成 H.264/AAC MP4

只應下載、改作及分享你有權使用嘅內容。YouTube 或歌詞服務嘅可用性亦可能隨時間改變。

## 開始使用（Windows）

目前專案已經有基本環境，可以直接雙擊 `start.bat`，或者在 PowerShell 執行：

```powershell
.\start.ps1
```

如要安裝高質 Demucs 人聲分離及 AI 歌詞對時：

```powershell
.\setup.ps1 -WithAI
```

亦可以直接雙擊 `install-ai.bat`。

AI 套件較大，而且第一次處理歌曲時會再下載 Demucs 及 Whisper 模型。安裝器會預先更新 Python 建立工具，避免 Whisper 長時間停喺建立隔離環境。冇安裝 AI 都可以使用「快速中心聲道」模式，但普通歌詞需要自行提供已有時間碼嘅 LRC。

可靠下載 YouTube 亦需要 Deno 2.3+ 或 Node.js 22+；安裝程式會自動檢查。程式會優先使用安全嘅 Windows 系統憑證庫，唔會關閉 HTTPS 驗證。

v0.5.1 起，Windows 安裝器會核對 JavaScript runtime 實際版本；搵唔到合規格 runtime 時會嘗試透過 winget 安裝 Deno。macOS 安裝器亦已修正系統內置 Bash 3.2 對中文標點旁變數嘅解析問題，避免安裝中途停止而漏裝 Streamlit。yt-dlp 會連同 EJS 套件更新至 2026.08.19。

## 開始使用（macOS）

下載並解壓縮 macOS 安裝包後，首次雙擊 `setup.command`。安裝完成後，雙擊 `start.command` 開啟程式。

`setup.command` 安裝基本功能；如要額外安裝高質 Demucs 人聲分離及 AI 歌詞對時，就雙擊 `install-ai.command`。後者會先執行相同基本安裝，再自動識別 Apple Silicon 或 Intel Mac，並選擇相容嘅 PyTorch、Demucs 同 Whisper 套件。遇到 PyPI 502／503 或短暫網絡錯誤時，macOS 安裝器會延長 pip 逾時並自動重試。

macOS 版透過 Homebrew 安裝 Python 3.12、包含 ASS 動態字幕支援嘅 `ffmpeg@7`，以及 Deno。如果尚未安裝 Homebrew，`setup.command` 會開啟官方安裝頁。新版 `start.command` 亦會自動偵測同修復缺少字幕濾鏡嘅舊版 FFmpeg。由於目前測試版未經 Apple Developer ID 簽署，首次開啟 `.command` 時可能需要在 Finder 按住 Control 點擊檔案，再選擇「開啟」。詳細步驟見安裝包內 `README-macOS.txt`。

## YouTube 下載疑難

- 一般公開影片：保持「使用瀏覽器 cookies」關閉。
- YouTube 顯示需要登入、確認年齡或「唔係機械人」：展開「下載有困難？」並選擇已登入 YouTube 嘅瀏覽器。
- 讀取 cookies 失敗：完全關閉所選瀏覽器後再試，或者關閉 cookies 選項。
- 私人、會員專屬、地區限制或已下架影片仍然需要相應觀看權限，程式唔會繞過限制。

使用帳戶 cookies 可能令 YouTube 暫時限制帳戶，應只喺必要時啟用，亦唔好短時間大量下載。

## 歌詞建議

程式會將搵歌詞放喺第一步。填寫歌名（必填）同歌手後，按「搜尋並確認同步歌詞」：程式先到 Kugeci 搜尋，搵唔到先使用後備服務。已有時間碼嘅 LRC 可以直接使用；普通逐行歌詞就要先完成 AI 句級對時及人工確認，之後先可以製作影片。

時間準確度由高至低：

1. 上載已校準時間嘅 `.lrc` 檔
2. 填寫準確歌名及歌手，使用自動同步歌詞（Kugeci 優先）
3. 貼上普通逐行歌詞，選擇廣東話、普通話或自動判斷，再按「下載音訊並自動對時」

AI 句級對時只下載分析所需音訊，所有辨認都喺本機完成。程式會顯示原曲播放器、每句開始秒數、配對信心及「需要覆核」標記；用戶可以修改時間同歌詞，再下載已校正 LRC。若之後選擇「AI 高質分離」製作影片，程式會重用對時階段產生嘅伴奏音軌，毋須再次執行 Demucs。

錄音室版本通常較容易對準；現場錄音、多人合唱、長混響、說唱或歌詞版本不同，都可能需要較多人工校正。第一期只產生句級時間，逐字變色仍會按每句長度平均分配。

字幕太早或太遲時，可以在「進階設定」以秒調整整體時間，支援一位小數，範圍係 -120.0 至 +120.0 秒。正數代表遲啲顯示。

## 輸出位置

完成嘅 MP4 會放在 `outputs`。處理中間檔會放在 `work/jobs`，成功後自動清除；如果處理失敗就會保留，方便診斷。

## Vercel 版本

正式項目頁：<https://karaoke-factory-hk.vercel.app>

Vercel 部署係項目介紹及下載頁。Streamlit 需要持續 WebSocket session，而 Demucs、FFmpeg、YouTube 下載同影片重新編碼亦超出一般 Vercel Functions 嘅運行模式，因此完整製作功能保留喺 Windows 或 macOS 本機版，避免雲端頁面看似可用但實際處理失敗。

## 開發及測試

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```
