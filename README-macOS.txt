K 歌工房 macOS 版
===================

適用系統
--------
- Apple Silicon（M1、M2、M3、M4 或更新）
- Intel Mac
- 建議 macOS Sonoma 14 或更新版本

首次安裝
--------
1. 解壓縮此 ZIP。
2. 雙擊 setup.command。
3. 如果尚未安裝 Homebrew，安裝程式會開啟 https://brew.sh/；完成 Homebrew 安裝後，再雙擊 setup.command。
4. 安裝完成後，雙擊 start.command 開啟 K 歌工房。

由舊版本更新
------------
解壓縮新版後可直接雙擊 start.command。程式會檢查 FFmpeg 有冇包含 ASS 動態字幕支援；如果發現舊版 Homebrew FFmpeg 缺少相關濾鏡，會自動執行 setup.command。安裝器會先修復或重裝 ffmpeg@7，仍然失敗就自動改用 ffmpeg-full。

高質 AI 人聲分離及歌詞對時
--------------------------
`setup.command` 只安裝基本功能，包括 YouTube 下載、快速中心聲道去人聲同影片字幕合成。

`install-ai.command` 會呼叫 `setup.command --with-ai`：先檢查／安裝全部基本功能，再額外安裝 Demucs、Whisper 及 PyTorch，提供高質 AI 人聲分離同句級歌詞對時。安裝器會使用已更新嘅 Python 建立工具，避免 Whisper 長時間停喺建立隔離環境。套件及模型檔案較大，第一次安裝與第一次分析歌曲需要較長時間。

如果搵唔到同步 LRC，可以貼上普通逐行歌詞，再選擇廣東話、普通話或自動判斷。程式會只下載分析用音訊、抽出主唱、產生初步句級時間，之後顯示播放器同校正表格。請特別覆核標示為「需要覆核」嘅句子，再下載 LRC 或繼續製作影片。所有辨認都喺本機完成。

第一期只會自動產生每句開始時間；逐字變色仍會喺句子範圍內平均分配。現場錄音、合唱、混響或歌詞版本不同可能需要較多人工校正。Intel Mac 可以使用此功能，但分析速度通常會比 Apple Silicon 慢。

如果 PyPI 暫時回傳 502／503，安裝器會增加 pip 連線重試及逾時時間，並將整個安裝步驟最多自動再試三次；無需立即改用另一個安裝檔。

Apple Silicon 會使用現行 PyTorch；Intel Mac 會自動使用最後提供 Intel macOS 預編譯套件的相容版本。兩種架構均可使用 FFmpeg 快速中心聲道模式。

macOS 安全提示
--------------
這個測試版本尚未經 Apple Developer ID 簽署。如果 macOS 阻止開啟 .command 檔案，請在 Finder 按住 Control 點擊該檔案，選擇「開啟」，再確認一次；亦可到「系統設定 > 私隱與保安」允許開啟。

字幕濾鏡疑難
------------
如果見到 `No such filter: 'ass'`，代表舊版一般 Homebrew FFmpeg 冇包含字幕濾鏡。請關閉 K 歌工房，再雙擊新版 `setup.command`；安裝器會自動重裝包含 libass 支援嘅 `ffmpeg@7`，有需要時再改用 `ffmpeg-full`，毋須自行輸入 Homebrew 指令。

使用限制
--------
只應下載及改作你有權使用的影片、音訊及歌詞。私人、會員專屬、地區限制或已下架影片仍須具有相應觀看權限。
