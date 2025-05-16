# nhentai 下載工具 (link2epub)

這是一個用於將 nhentai 內容下載並轉換為 EPUB 電子書的工具。支援 RSS 批量下載，可選擇直接使用外部圖片連結或下載圖片，還可以自動上傳到 AList 伺服器。

## Docker 部署

### 快速啟動

```bash
docker run -d \
  --name link2epub \
  -p 5000:5000 \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=your_secure_password \
  -e ALIST_BASE=http://your-alist-server \
  -e ALIST_USERNAME=your_alist_username \
  -e ALIST_PASSWORD=your_alist_password \
  -v /your/data/path:/app/output \
  ghcr.io/yourusername/link2epub:latest
```

### 環境變數

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `ADMIN_USERNAME` | 管理員用戶名 | admin |
| `ADMIN_PASSWORD` | 管理員密碼 | admin123 |
| `SECRET_KEY` | Flask 密鑰 | link2epub-secret-key |
| `ALIST_BASE` | AList 伺服器網址（不含尾部斜線） | http://your-alist-server |
| `ALIST_USERNAME` | AList 登入用戶名 | your_username |
| `ALIST_PASSWORD` | AList 登入密碼 | your_password |
| `ALIST_REMOTE_DIR` | AList 上傳目錄路徑 | /book/nh |

### 掛載點

| 掛載點 | 說明 |
|--------|------|
| `/app/output` | 輸出目錄，包含下載的 EPUB 文件和資料庫 |
| `/app/nhentai_rss.opml` | OPML 訂閱文件（可選） |

### Web 界面

部署完成後，可以通過 http://your-server-ip:5000 訪問 Web 界面，使用設定的管理員賬戶登入。

Web 界面功能：
- RSS 訂閱管理（添加、刪除、檢查有效性）
- 下載任務管理
- 臨時文件監控
- 系統維護（清理臨時文件）

## AList 設定

要啟用上傳到 AList 功能，請確保已正確設定 AList 相關環境變數：

1. `ALIST_BASE`: AList 伺服器的完整網址，例如 `https://alist.example.com`（不含尾部斜線）
2. `ALIST_USERNAME`: 有上傳權限的 AList 用戶名
3. `ALIST_PASSWORD`: 用戶密碼
4. `ALIST_REMOTE_DIR`: AList 上傳目錄的路徑，例如 `/book/nh`

您可以在 docker-compose.yml 文件中配置這些環境變數，或在運行 Docker 容器時直接指定。

## 基本使用方法

### 下載並自動上傳到 AList 伺服器

預設的 OPML 檔案路徑為 `nhentai_rss.opml`，包含多個 nhentai 搜尋結果的 RSS 訂閱。下載完成後會自動上傳至 AList 伺服器。

```bash
python main.py -o nhentai_rss.opml -u
```

### 僅下載不上傳

```bash
python main.py -o nhentai_rss.opml
```

### 處理已下載但未上傳的文件

目前程式在處理過程中會將每個下載項目的上傳狀態記錄在資料庫中。如果有些檔案已下載但未上傳（例如因為網路問題或之前未啟用上傳選項），可以使用以下方法將其上傳：

1. 手動查詢資料庫找出未上傳的檔案：
```bash
# 使用 SQLite 命令列工具
sqlite3 output/nh/downloaded.db "SELECT file_path FROM downloaded WHERE uploaded = 0;"
```

2. 編寫簡單的腳本來上傳這些檔案（示例）：
```python
# upload_missing.py
import sqlite3
import os
from main import NHentaiDownloader

# 初始化下載器（僅用於上傳功能）
downloader = NHentaiDownloader(upload_to_alist=True)

# 連接資料庫
conn = sqlite3.connect('output/nh/downloaded.db')
cursor = conn.cursor()

# 查詢所有已下載但未上傳的檔案
cursor.execute("SELECT id, title, url, file_path FROM downloaded WHERE uploaded = 0")
files = cursor.fetchall()

print(f"找到 {len(files)} 個未上傳的檔案")

for file_id, title, url, file_path in files:
    if os.path.exists(file_path):
        print(f"正在上傳: {title}")
        # 使用與原始程式相同的時間戳目錄格式
        time_dir = os.path.basename(os.path.dirname(file_path))
        remote_dir = f"/book/nh/{time_dir}"
        
        # 嘗試上傳
        if downloader.upload_to_alist_server(file_path, remote_dir):
            # 更新上傳狀態
            cursor.execute("UPDATE downloaded SET uploaded = 1 WHERE id = ?", (file_id,))
            conn.commit()
            print(f"上傳成功: {title}")
        else:
            print(f"上傳失敗: {title}")
    else:
        print(f"檔案不存在: {file_path}")

conn.close()
print("完成")
```

### 自訂輸出目錄

```bash
python main.py -o nhentai_rss.opml -d 自訂輸出目錄 -u
```

### 使用外部圖片連結（不下載圖片）

```bash
python main.py -o nhentai_rss.opml -e -u
```

### 使用單一 RSS URL

```bash
python main.py -r https://rsshub.example.com/nhentai/search/關鍵詞/detail -u
```

## 完整參數說明

| 參數 | 說明 |
|------|------|
| `-o, --opml` | OPML 檔案路徑，包含多個 RSS 來源 |
| `-r, --rss` | 單一 RSS URL |
| `-d, --output-dir` | 基本輸出目錄 (預設: output/nh) |
| `-e, --external` | 使用外部圖片連結 (不下載圖片) |
| `-u, --upload` | 上傳到 AList 伺服器 |

## 功能特色

- 自動檢查並跳過已下載項目
- 支援標籤信息提取（需要 nhentai_info_viewer 模組）
- 圖片自動轉換為 EPUB 適合的格式
- 資料庫記錄下載歷史和上傳狀態
- 完整的標籤信息頁面
- 生成的 EPUB 檔案包含原始標題、標籤和分類信息
- 處理一本即上傳一本，不會等到全部處理完畢
- Docker容器化部署
- Web管理界面
- 定時清理臨時文件
- 支持恢復失敗的下載

## 注意事項

- 請確保網路連接穩定
- 若啟用上傳功能，請確認 AList 伺服器配置正確
- 使用外部連結模式可能導致 EPUB 在某些閱讀器中無法正常顯示圖片
- 預設會在輸出目錄中建立以時間戳命名的子目錄
- 每個 EPUB 檔案處理完成後會立即嘗試上傳，而不是等待全部處理完成

## 資料庫說明

程式會在輸出目錄中建立 `downloaded.db` 資料庫檔案，用於記錄已下載項目和上傳狀態。資料表結構包含以下欄位：
- id: 自動遞增主鍵
- title: 標題
- url: 來源URL
- rss_source: RSS來源
- download_date: 下載日期
- file_path: 檔案路徑
- uploaded: 上傳狀態(0:未上傳, 1:已上傳) 