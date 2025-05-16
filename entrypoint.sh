#!/bin/bash

# 啟動cron服務
service cron start
echo "已啟動定時清理服務"

# 檢查資料庫和目錄
python -c "import sqlite3; conn = sqlite3.connect('output/nh/downloaded.db'); conn.execute('CREATE TABLE IF NOT EXISTS downloaded (id INTEGER PRIMARY KEY, title TEXT, url TEXT UNIQUE, rss_source TEXT, download_date TEXT, file_path TEXT, uploaded INTEGER DEFAULT 0)'); conn.close()"
python -c "import sqlite3; conn = sqlite3.connect('output/nh/temp_tracking.db'); conn.execute('CREATE TABLE IF NOT EXISTS temp_files (id INTEGER PRIMARY KEY, item_url TEXT, temp_dir TEXT, status TEXT, created_time TEXT, completed_time TEXT, error_message TEXT)'); conn.close()"
echo "資料庫檢查完成"

# 檢查是否有預先設定的RSS文件
if [ ! -s nhentai_rss.opml ]; then
    echo "未找到RSS訂閱，創建預設檔案"
    echo '<opml version="2.0"><body></body></opml>' > nhentai_rss.opml
fi

# 設置默認管理員帳號密碼（如果環境變數未設置）
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"
echo "管理員帳號: $ADMIN_USERNAME"

# 啟動Web服務
echo "啟動Web服務..."
exec python web_ui.py 