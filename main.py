#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
import datetime
import feedparser
import requests
import sqlite3
import argparse
import uuid
import re
import shutil
import logging
import json
import urllib.parse
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from ebooklib import epub
from PIL import Image
from io import BytesIO

# 引入 nhentai_info_viewer 模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from nhentai_info_viewer import NHentaiInfoViewer
except ImportError:
    print("無法導入 NHentaiInfoViewer 模組，標籤功能將不可用")
    NHentaiInfoViewer = None

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("nhentai_downloader.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# AList 配置
ALIST_BASE = os.environ.get("ALIST_BASE", "http://your-alist-server")  # 末尾不要加 '/'
USERNAME = os.environ.get("ALIST_USERNAME", "your_username")
PASSWORD = os.environ.get("ALIST_PASSWORD", "your_password")
REMOTE_BASE_DIR = os.environ.get("ALIST_REMOTE_DIR", "/book/nh")  # AList 端的基礎目錄

class NHentaiDownloader:
    def __init__(self, base_dir='output/nh', use_external_links=False, upload_to_alist=False):
        self.base_dir = base_dir
        self.use_external_links = use_external_links
        self.upload_to_alist = upload_to_alist
        
        # 使用當前時間作為資料夾名稱
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.output_dir = os.path.join(self.base_dir, timestamp)
        self.timestamp_dir = timestamp  # 僅保存時間戳目錄名
        
        # 臨時目錄用於儲存下載的圖片
        self.temp_dir = os.path.join(self.base_dir, 'temp')
        
        # 確保資料夾存在
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # 初始化資料庫
        self.db_path = os.path.join(self.base_dir, 'downloaded.db')
        self.init_database()
        
        # 初始化臨時檔案追蹤資料庫
        self.temp_db_path = self.init_temp_database()
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 如果啟用上傳，則獲取 AList 令牌
        self.alist_token = None
        if self.upload_to_alist:
            self.alist_token = self.get_alist_token()
        
        logger.info(f"初始化完成，輸出目錄: {self.output_dir}")
    
    def init_database(self):
        """初始化 SQLite 資料庫"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloaded (
                id INTEGER PRIMARY KEY,
                title TEXT,
                url TEXT UNIQUE,
                rss_source TEXT,
                download_date TEXT,
                file_path TEXT,
                uploaded INTEGER DEFAULT 0
            )
            ''')
            conn.commit()
            conn.close()
            logger.info(f"資料庫初始化完成: {self.db_path}")
        except Exception as e:
            logger.error(f"資料庫初始化失敗: {e}")
            sys.exit(1)
    
    def is_downloaded(self, url):
        """檢查URL是否已下載"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM downloaded WHERE url = ?", (url,))
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except Exception as e:
            logger.error(f"檢查下載狀態失敗: {e}")
            return False
    
    def mark_as_downloaded(self, title, url, rss_source, file_path, uploaded=0):
        """將URL標記為已下載"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                "INSERT INTO downloaded (title, url, rss_source, download_date, file_path, uploaded) VALUES (?, ?, ?, ?, ?, ?)",
                (title, url, rss_source, now, file_path, uploaded)
            )
            conn.commit()
            conn.close()
            logger.info(f"已標記為已下載: {title}")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"URL已存在於資料庫: {url}")
            return False
        except Exception as e:
            logger.error(f"標記下載狀態失敗: {e}")
            return False
    
    def update_upload_status(self, url, uploaded=1):
        """更新上傳狀態"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE downloaded SET uploaded = ? WHERE url = ?", (uploaded, url))
            conn.commit()
            conn.close()
            logger.info(f"已更新上傳狀態: {url}")
            return True
        except Exception as e:
            logger.error(f"更新上傳狀態失敗: {e}")
            return False
    
    def parse_opml(self, opml_file):
        """解析OPML檔案，獲取RSS來源"""
        try:
            tree = ET.parse(opml_file)
            root = tree.getroot()
            
            rss_sources = []
            for outline in root.findall(".//outline"):
                if outline.get("type") == "rss" and outline.get("xmlUrl"):
                    rss_sources.append({
                        "title": outline.get("title", ""),
                        "url": outline.get("xmlUrl", ""),
                        "html_url": outline.get("htmlUrl", "")
                    })
            
            logger.info(f"從OPML檔案找到 {len(rss_sources)} 個RSS來源")
            return rss_sources
        except Exception as e:
            logger.error(f"解析OPML檔案失敗: {e}")
            return []
    
    def parse_rss(self, rss_url):
        """解析RSS內容"""
        logger.info(f"開始解析RSS: {rss_url}")
        feed = feedparser.parse(rss_url)
        
        if not feed.entries:
            logger.warning("未找到RSS條目")
            return []
        
        logger.info(f"找到 {len(feed.entries)} 個條目")
        return feed.entries
    
    def download_image(self, img_url, save_path):
        """下載圖片並保存到指定路徑"""
        max_retries = 3
        retries = 0
        
        while retries < max_retries:
            try:
                if retries > 0:
                    logger.info(f"重試下載圖片 ({retries}/{max_retries}): {img_url}")
                    # 添加隨機延遲，避免連續請求
                    time.sleep(1 + retries)
                
                response = requests.get(img_url, headers=self.headers, timeout=30)
                response.raise_for_status()
                
                # 確保圖片目錄存在
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                
                # 保存圖片
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                
                # 轉換為 JPEG 格式 (EPUB 更好支持)
                try:
                    img = Image.open(save_path)
                    if img.format != 'JPEG':
                        img = img.convert('RGB')
                        jpg_path = save_path.replace('.webp', '.jpg')
                        img.save(jpg_path, 'JPEG')
                        os.remove(save_path)  # 刪除原圖片
                        save_path = jpg_path
                except Exception as e:
                    logger.error(f"圖片轉換錯誤: {e}")
                
                # 成功下載並處理圖片
                return save_path
                
            except Exception as e:
                retries += 1
                logger.warning(f"下載圖片失敗 (嘗試 {retries}/{max_retries}): {img_url}, 錯誤: {e}")
                
                # 如果已達到最大重試次數，記錄最終錯誤
                if retries >= max_retries:
                    logger.error(f"下載圖片最終失敗 (已重試 {max_retries} 次): {img_url}")
                    return None
        
        return None
    
    def extract_images(self, html_content):
        """從HTML中提取圖片URL"""
        soup = BeautifulSoup(html_content, 'html.parser')
        img_tags = soup.find_all('img')
        
        image_urls = []
        for i, img in enumerate(img_tags):
            if 'src' in img.attrs:
                img_url = img['src']
                image_urls.append(img_url)
                
                # 顯示進度
                if i % 10 == 0:
                    logger.debug(f"處理圖片連結: {i+1}/{len(img_tags)}")
        
        return image_urls
    
    def download_images(self, image_urls, item_dir):
        """批量下載圖片並返回本地路徑列表"""
        downloaded_images = []
        
        for i, img_url in enumerate(image_urls):
            file_ext = os.path.splitext(img_url)[1]
            if not file_ext:
                file_ext = '.webp'  # 預設擴展名
            
            img_filename = f"image_{i+1:03d}{file_ext}"
            img_path = os.path.join(item_dir, img_filename)
            
            downloaded_path = self.download_image(img_url, img_path)
            if downloaded_path:
                downloaded_images.append(downloaded_path)
                
                # 顯示進度
                if i % 5 == 0 or i == len(image_urls) - 1:
                    logger.info(f"已下載 {i+1}/{len(image_urls)} 張圖片")
        
        return downloaded_images
    
    def create_epub(self, title, image_urls, output_path, item_temp_dir=None, url=None):
        """建立EPUB檔案"""
        book = epub.EpubBook()
        
        # 設置元數據
        book.set_identifier(str(uuid.uuid4()))
        book.set_title(title)
        book.set_language('zh-TW')
        
        # 添加樣式
        style = '''
        @namespace epub "http://www.idpf.org/2007/ops";
        body {
            font-family: sans-serif;
            text-align: center;
        }
        img {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
        }
        .image-container {
            margin: 1em 0;
        }
        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 1em;
        }
        h2 {
            color: #555;
            border-bottom: 1px solid #ddd;
            padding-bottom: 0.5em;
            margin-top: 1.5em;
            text-align: left;
        }
        .tag {
            display: inline-block;
            background-color: #f0f0f0;
            padding: 5px 10px;
            margin: 5px;
            border-radius: 3px;
        }
        .tags-container {
            text-align: left;
            margin: 1em 2em;
        }
        '''
        
        css = epub.EpubItem(
            uid="style_default",
            file_name="style/default.css",
            media_type="text/css",
            content=style
        )
        book.add_item(css)
        
        # 嘗試獲取標籤信息
        gallery_data = None
        if url and 'nhentai.net/g/' in url and NHentaiInfoViewer:
            try:
                logger.info(f"正在獲取標籤信息: {url}")
                info_viewer = NHentaiInfoViewer(output_dir=self.temp_dir)
                gallery_data = info_viewer.fetch_gallery_data(url)
                if gallery_data:
                    logger.info(f"成功獲取標籤信息: {len(gallery_data.get('tags', []))} 個標籤")
            except Exception as e:
                logger.error(f"獲取標籤信息失敗: {e}")
        
        # 如果使用外部連結，直接使用URL；否則下載圖片
        if self.use_external_links:
            # 使用外部連結
            logger.info("使用外部連結模式創建EPUB")
            images = image_urls
            is_local_file = False
        else:
            # 下載圖片
            logger.info("使用下載圖片模式創建EPUB")
            if not item_temp_dir:
                # 創建臨時目錄
                item_temp_dir = os.path.join(self.temp_dir, str(uuid.uuid4()))
                os.makedirs(item_temp_dir, exist_ok=True)
            
            # 下載所有圖片
            images = self.download_images(image_urls, item_temp_dir)
            is_local_file = True
        
        # 建立章節並添加圖片
        chapters = []
        
        # 如果有圖片且是本地文件，設置第一張為封面
        if images and not self.use_external_links:
            cover_path = images[0]
            with open(cover_path, 'rb') as f:
                cover_content = f.read()
            book.set_cover("cover.jpg", cover_content)
        
        # 創建標籤頁作為第一頁
        tags_chapter = epub.EpubHtml(
            title='標籤信息',
            file_name='tags.xhtml',
            lang='zh-TW'
        )
        
        # 構建標籤頁內容
        tags_content = f'''
        <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
        <head>
            <title>{title} - 標籤信息</title>
            <link rel="stylesheet" type="text/css" href="style/default.css" />
        </head>
        <body>
            <h1>{title}</h1>
        '''
        
        # 如果有標籤數據，添加標籤信息
        if gallery_data and 'categorized_tags' in gallery_data:
            categorized_tags = gallery_data.get('categorized_tags', {})
            
            # 定義標籤類型的中文名稱
            tag_type_names = {
                "artist": "藝術家",
                "character": "角色",
                "group": "社團/組織",
                "language": "語言",
                "parody": "原作",
                "tag": "標籤",
                "category": "分類",
                "other": "其他"
            }
            
            # 添加分類標籤
            for tag_type, tags in categorized_tags.items():
                tag_type_display = tag_type_names.get(tag_type, tag_type)
                tags_content += f'<h2>{tag_type_display}</h2>\n<div class="tags-container">'
                
                for tag in tags:
                    # 移除標籤後的數字部分（例如 "big breasts 182K" 變為 "big breasts"）
                    tag_name = tag['name'].split(' ')[0] if ' ' in tag['name'] and tag['name'].split(' ')[1].strip().lower().endswith(('k', 'k+')) else tag['name']
                    tags_content += f'<span class="tag">{tag_name}</span>'
                
                tags_content += '</div>'
        else:
            tags_content += '<p>無法獲取標籤信息</p>'
        
        tags_content += '''
        </body>
        </html>
        '''
        
        tags_chapter.content = tags_content
        tags_chapter.add_item(css)
        book.add_item(tags_chapter)
        chapters.append(tags_chapter)
        
        for i, img_item in enumerate(images):
            chapter = epub.EpubHtml(
                title=f'{i+1}',
                file_name=f'page_{i+1:03d}.xhtml',
                lang='zh-TW'
            )
            
            if is_local_file:
                # 本地圖片模式
                img_path = img_item
                img_filename = os.path.basename(img_path)
                img_id = f'image_{i+1:03d}'
                
                # 讀取圖片並添加到EPUB
                with open(img_path, 'rb') as f:
                    img_content = f.read()
                
                # 判斷圖片類型
                media_type = 'image/jpeg' if img_path.endswith('.jpg') else 'image/webp'
                
                # 添加圖片到EPUB
                img_item_obj = epub.EpubItem(
                    uid=img_id,
                    file_name=f'images/{img_filename}',
                    media_type=media_type,
                    content=img_content
                )
                book.add_item(img_item_obj)
                
                # 在章節中引用圖片
                chapter.content = f'''
                <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
                <head>
                    <title>{title} - {i+1}</title>
                    <link rel="stylesheet" type="text/css" href="style/default.css" />
                </head>
                <body>
                    <div class="image-container">
                        <img src="images/{img_filename}" alt="圖片 {i+1}" />
                    </div>
                </body>
                </html>
                '''
            else:
                # 外部連結模式
                chapter.content = f'''
                <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
                <head>
                    <title>{title} - {i+1}</title>
                    <link rel="stylesheet" type="text/css" href="style/default.css" />
                </head>
                <body>
                    <div class="image-container">
                        <img src="{img_item}" alt="圖片 {i+1}" />
                    </div>
                </body>
                </html>
                '''
            
            chapter.add_item(css)
            book.add_item(chapter)
            chapters.append(chapter)
        
        # 添加目錄和導航
        book.toc = chapters
        book.spine = ['nav'] + chapters
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # 寫入檔案
        epub.write_epub(output_path, book, {})
        logger.info(f"已建立EPUB: {output_path}")
        
        return output_path
    
    def get_alist_token(self):
        """取得 AList API 的 Token"""
        try:
            auth_resp = requests.post(
                f"{ALIST_BASE}/api/auth/login",
                json={"username": USERNAME, "password": PASSWORD},
                timeout=30,
            )
            auth_resp.raise_for_status()
            token = auth_resp.json()["data"]["token"]
            logger.info("已取得 AList 認證 Token")
            return token
        except Exception as e:
            logger.error(f"獲取 AList Token 失敗: {e}")
            return None
    
    def upload_to_alist_server(self, local_path, remote_dir):
        """上傳檔案到 AList 伺服器"""
        if not self.alist_token:
            logger.error("缺少 AList Token，無法上傳")
            return False
        
        try:
            remote_name = os.path.basename(local_path)
            remote_path = f"{remote_dir.rstrip('/')}/{remote_name}"
            file_path_header = urllib.parse.quote(remote_path)
            
            with open(local_path, "rb") as fp:
                file_size = os.fstat(fp.fileno()).st_size
                headers = {
                    "Authorization": self.alist_token,
                    "File-Path": file_path_header,
                    "Content-Length": str(file_size),
                }
                files = {"file": fp}
                
                logger.info(f"開始上傳: {local_path} -> {remote_path}")
                upload_resp = requests.put(
                    f"{ALIST_BASE}/api/fs/form",
                    headers=headers,
                    files=files,
                    timeout=300,
                )
                upload_resp.raise_for_status()
                logger.info(f"上傳完成: {remote_path}")
                logger.debug(f"AList 回應: {upload_resp.json()}")
                return True
        except Exception as e:
            logger.error(f"上傳到 AList 失敗: {e}")
            return False
    
    def init_temp_database(self):
        """初始化臨時檔案追蹤資料庫"""
        try:
            temp_db_path = os.path.join(self.base_dir, 'temp_tracking.db')
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS temp_files (
                id INTEGER PRIMARY KEY,
                item_url TEXT,
                temp_dir TEXT,
                status TEXT,
                created_time TEXT,
                completed_time TEXT,
                error_message TEXT
            )
            ''')
            conn.commit()
            conn.close()
            logger.info(f"臨時檔案追蹤資料庫初始化完成: {temp_db_path}")
            return temp_db_path
        except Exception as e:
            logger.error(f"臨時檔案追蹤資料庫初始化失敗: {e}")
            return None

    def track_temp_dir(self, item_url, temp_dir):
        """記錄臨時目錄與項目的關係"""
        try:
            conn = sqlite3.connect(self.temp_db_path)
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                "INSERT INTO temp_files (item_url, temp_dir, status, created_time) VALUES (?, ?, ?, ?)",
                (item_url, temp_dir, "processing", now)
            )
            conn.commit()
            conn.close()
            logger.info(f"已記錄臨時目錄: {temp_dir} 用於 {item_url}")
        except Exception as e:
            logger.error(f"記錄臨時目錄失敗: {e}")

    def update_temp_dir_status(self, temp_dir, status, error_message=None):
        """更新臨時目錄狀態"""
        try:
            conn = sqlite3.connect(self.temp_db_path)
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if error_message:
                cursor.execute(
                    "UPDATE temp_files SET status = ?, completed_time = ?, error_message = ? WHERE temp_dir = ?",
                    (status, now, error_message, temp_dir)
                )
            else:
                cursor.execute(
                    "UPDATE temp_files SET status = ?, completed_time = ? WHERE temp_dir = ?",
                    (status, now, temp_dir)
                )
            
            conn.commit()
            conn.close()
            logger.info(f"已更新臨時目錄狀態: {temp_dir} -> {status}")
        except Exception as e:
            logger.error(f"更新臨時目錄狀態失敗: {e}")

    def recover_failed_downloads(self):
        """恢復失敗的下載"""
        try:
            conn = sqlite3.connect(self.temp_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT item_url, temp_dir FROM temp_files WHERE status = 'failed'")
            failed_items = cursor.fetchall()
            conn.close()
            
            recovered_count = 0
            for item_url, temp_dir in failed_items:
                logger.info(f"嘗試恢復失敗的下載: {item_url}")
                # 這裡可以實現具體的恢復邏輯，例如重新解析 RSS 獲取項目信息等
                # 目前實現一個簡單的標記更新
                self.update_temp_dir_status(temp_dir, "pending_recovery")
                recovered_count += 1
                
            return recovered_count
        except Exception as e:
            logger.error(f"恢復失敗的下載出錯: {e}")
            return 0
    
    def process_item(self, item, rss_source):
        """處理單個 RSS 條目"""
        try:
            title = item.title
            url = item.link
            
            # 檢查是否已下載
            if self.is_downloaded(url):
                logger.info(f"已跳過 (之前下載過): {title}")
                return None
            
            # 清理標題，使其適合作為檔名
            safe_title = re.sub(r'[\\/*?:"<>|]', '', title)[:100]
            logger.info(f"\n處理: {safe_title}")
            
            # 提取圖片連結
            image_urls = self.extract_images(item.description)
            
            if not image_urls:
                logger.warning(f"未找到圖片: {safe_title}")
                return None
            
            logger.info(f"找到 {len(image_urls)} 張圖片連結")
            
            # 創建臨時目錄
            item_temp_dir = None
            if not self.use_external_links:
                item_temp_dir = os.path.join(self.temp_dir, str(uuid.uuid4()))
                os.makedirs(item_temp_dir, exist_ok=True)
                
                # 記錄臨時目錄與 URL 的關係
                self.track_temp_dir(url, item_temp_dir)
            
            # 創建輸出檔案路徑
            epub_filename = f"{safe_title}.epub"
            output_path = os.path.join(self.output_dir, epub_filename)
            
            try:
                # 建立 EPUB
                self.create_epub(title, image_urls, output_path, item_temp_dir, url)
                
                # 成功處理，更新臨時目錄狀態
                if item_temp_dir:
                    self.update_temp_dir_status(item_temp_dir, "completed")
                
                # 上傳到 AList（如果啟用）
                uploaded = 0
                if self.upload_to_alist and os.path.exists(output_path):
                    remote_dir = f"{REMOTE_BASE_DIR}/{self.timestamp_dir}"
                    if self.upload_to_alist_server(output_path, remote_dir):
                        uploaded = 1
                
                # 標記為已下載
                self.mark_as_downloaded(title, url, rss_source, output_path, uploaded)
                
                # 清理臨時目錄 (只有在成功完成時)
                if item_temp_dir and os.path.exists(item_temp_dir):
                    try:
                        shutil.rmtree(item_temp_dir)
                        logger.debug(f"已清理臨時目錄: {item_temp_dir}")
                    except Exception as e:
                        logger.warning(f"清理臨時目錄失敗: {e}")
            
            except Exception as e:
                logger.error(f"處理項目時出錯: {e}")
                if item_temp_dir:
                    self.update_temp_dir_status(item_temp_dir, "failed", str(e))
                return None
            
            return output_path
        except Exception as e:
            logger.error(f"處理項目時出錯: {e}")
            return None
    
    def process_rss(self, rss_source):
        """處理一個 RSS 來源的所有條目"""
        logger.info(f"\n開始處理 RSS 來源: {rss_source['title']}")
        entries = self.parse_rss(rss_source['url'])
        if not entries:
            return []
        
        results = []
        for i, item in enumerate(entries):
            logger.info(f"\n處理項目 {i+1}/{len(entries)}")
            result = self.process_item(item, rss_source['url'])
            if result:
                results.append(result)
        
        return results
    
    def run(self, opml_file=None, rss_url=None):
        """執行下載流程"""
        start_time = time.time()
        all_results = []
        
        # 嘗試恢復失敗的下載
        recovered_count = self.recover_failed_downloads()
        if recovered_count > 0:
            logger.info(f"找到 {recovered_count} 個失敗的下載任務待恢復")
        
        # 處理 OPML 檔案
        if opml_file and os.path.exists(opml_file):
            rss_sources = self.parse_opml(opml_file)
            for source in rss_sources:
                results = self.process_rss(source)
                all_results.extend(results)
        
        # 處理單一 RSS URL
        elif rss_url:
            source = {"title": "Custom RSS", "url": rss_url, "html_url": ""}
            results = self.process_rss(source)
            all_results.extend(results)
        
        elapsed_time = time.time() - start_time
        logger.info(f"\n完成! 總共處理 {len(all_results)} 個項目，耗時 {elapsed_time:.2f} 秒")
        
        # 清理臨時目錄 (但保留失敗任務的目錄)
        try:
            conn = sqlite3.connect(self.temp_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT temp_dir FROM temp_files WHERE status != 'completed'")
            active_temp_dirs = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            # 只清理空目錄或已完成的臨時目錄
            for root, dirs, files in os.walk(self.temp_dir, topdown=False):
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    if dir_path not in active_temp_dirs and (len(os.listdir(dir_path)) == 0):
                        try:
                            os.rmdir(dir_path)
                            logger.debug(f"已清理臨時目錄: {dir_path}")
                        except:
                            pass
        except Exception as e:
            logger.warning(f"清理臨時目錄時出錯: {e}")
        
        return all_results


def main():
    parser = argparse.ArgumentParser(description='nhentai RSS 下載工具')
    parser.add_argument('-o', '--opml', help='OPML 檔案路徑')
    parser.add_argument('-r', '--rss', help='單一 RSS URL')
    parser.add_argument('-d', '--output-dir', default='output/nh', help='基本輸出目錄 (預設: output/nh)')
    parser.add_argument('-e', '--external', action='store_true', help='使用外部圖片連結 (不下載圖片)')
    parser.add_argument('-u', '--upload', action='store_true', help='上傳到 AList 伺服器')
    
    args = parser.parse_args()
    
    if not args.opml and not args.rss:
        parser.error("請提供 OPML 檔案 (-o) 或 RSS URL (-r)")
    
    downloader = NHentaiDownloader(
        base_dir=args.output_dir,
        use_external_links=args.external,
        upload_to_alist=args.upload
    )
    
    downloader.run(opml_file=args.opml, rss_url=args.rss)


if __name__ == "__main__":
    main() 