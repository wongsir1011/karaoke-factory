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
解壓縮新版後可直接雙擊 start.command。程式會檢查 FFmpeg 有冇包含 ASS 動態字幕支援；如果發現舊版 Homebrew FFmpeg 缺少相關濾鏡，會自動執行 setup.command 安裝相容版本。

高質 AI 人聲分離
-----------------
雙擊 install-ai.command 安裝 Demucs AI 模式。套件及模型檔案較大，第一次安裝與第一次處理歌曲需要較長時間。

Apple Silicon 會使用現行 PyTorch；Intel Mac 會自動使用最後提供 Intel macOS 預編譯套件的相容版本。兩種架構均可使用 FFmpeg 快速中心聲道模式。

macOS 安全提示
--------------
這個測試版本尚未經 Apple Developer ID 簽署。如果 macOS 阻止開啟 .command 檔案，請在 Finder 按住 Control 點擊該檔案，選擇「開啟」，再確認一次；亦可到「系統設定 > 私隱與保安」允許開啟。

字幕濾鏡疑難
------------
如果見到 `No such filter: 'ass'`，代表舊版一般 Homebrew FFmpeg 冇包含字幕濾鏡。請關閉 K 歌工房，再雙擊新版 `setup.command`；安裝程式會改用包含 libass 支援嘅 `ffmpeg@7`。

使用限制
--------
只應下載及改作你有權使用的影片、音訊及歌詞。私人、會員專屬、地區限制或已下架影片仍須具有相應觀看權限。
