FROM python:3.9-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    libxml2-dev \
    libxslt-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 複製必要的檔案
COPY requirements.txt .
COPY *.py ./ 
COPY nhentai_rss.opml .

# 確保目錄存在
RUN mkdir -p output/nh output/nh_info temp text2epub2upload s

# 安裝Python依賴
RUN pip install --no-cache-dir -r requirements.txt

# 安裝Web界面所需的依賴
RUN pip install --no-cache-dir flask flask-login flask-wtf

# 設定環境變數
ENV PYTHONUNBUFFERED=1

# 暴露Web界面端口
EXPOSE 5000

# 執行清理任務的cron作業
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*
COPY cron_cleanup /etc/cron.d/cleanup
RUN chmod 0644 /etc/cron.d/cleanup && crontab /etc/cron.d/cleanup

# 啟動腳本
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"] 