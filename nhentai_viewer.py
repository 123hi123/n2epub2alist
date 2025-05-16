#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import requests
import re
import time
import argparse
import json
import logging
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
from ebooklib import epub
import uuid
import shutil
import datetime

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("nhentai_viewer.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class NHentaiViewer:
    def __init__(self, output_dir='output/nh'):
        self.output_dir = output_dir
        
        # 創建臨時目錄用於儲存下載的圖片
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.temp_dir = os.path.join(output_dir, 'temp', str(uuid.uuid4()))
        self.gallery_dir = os.path.join(output_dir, timestamp)
        
        # 確保資料夾存在
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.gallery_dir, exist_ok=True)
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        logger.info(f"初始化完成，臨時目錄: {self.temp_dir}")
        logger.info(f"圖庫目錄: {self.gallery_dir}")
    
    def fetch_gallery_data(self, url):
        """擷取畫廊數據"""
        logger.info(f"正在獲取畫廊數據: {url}")
        
        try:
            # 獲取網頁內容
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取標題、標籤等元數據
            title = soup.select_one('#info h1')
            title = title.text.strip() if title else "未知標題"
            
            original_title = soup.select_one('#info h2')
            original_title = original_title.text.strip() if original_title else ""
            
            # 獲取圖片數量和圖像URL模式
            gallery_id = url.split('/')[-2]  # 從URL提取畫廊ID
            
            # 提取媒體ID
            media_id_pattern = r'"media_id":"([^"]+)"'
            media_id_match = re.search(media_id_pattern, response.text)
            media_id = media_id_match.group(1) if media_id_match else None
            
            # 提取文件擴展名
            extensions_pattern = r'"images":\s*{[^}]*"extension":\s*(\[[^\]]+\])'
            extensions_match = re.search(extensions_pattern, response.text)
            extensions_json = extensions_match.group(1) if extensions_match else '[]'
            
            # 解析擴展名數據
            try:
                extensions = json.loads(extensions_json)
            except:
                extensions = []
            
            # 提取頁數
            num_pages_pattern = r'"num_pages":\s*(\d+)'
            num_pages_match = re.search(num_pages_pattern, response.text)
            num_pages = int(num_pages_match.group(1)) if num_pages_match else 0
            
            # 獲取標籤
            tags = []
            tag_elements = soup.select('#tags .tag')
            for tag_element in tag_elements:
                tag_name_element = tag_element.select_one('.name')
                tag_count_element = tag_element.select_one('.count')
                
                if tag_name_element:
                    tag_name = tag_name_element.text.strip()
                    tag_count = tag_count_element.text.strip() if tag_count_element else ""
                    tags.append({"name": tag_name, "count": tag_count})
            
            # 獲取縮圖
            thumbnails = []
            thumb_elements = soup.select('#thumbnail-container .thumb-container img')
            for thumb in thumb_elements:
                if 'data-src' in thumb.attrs:
                    thumbnails.append(thumb['data-src'])
                elif 'src' in thumb.attrs:
                    thumbnails.append(thumb['src'])
            
            # 構建每頁的圖片URL
            image_urls = []
            extension_map = {
                'j': 'jpg',
                'p': 'png',
                'g': 'gif'
            }
            
            for i in range(1, num_pages + 1):
                # 獲取此頁的擴展名
                ext_index = i - 1
                ext_code = extensions[ext_index] if ext_index < len(extensions) else 'j'
                ext = extension_map.get(ext_code, 'jpg')
                
                # 構建圖片URL
                img_url = f"https://i.nhentai.net/galleries/{media_id}/{i}.{ext}"
                image_urls.append(img_url)
            
            # 返回收集的數據
            gallery_data = {
                "title": title,
                "original_title": original_title,
                "gallery_id": gallery_id,
                "media_id": media_id,
                "num_pages": num_pages,
                "tags": tags,
                "thumbnails": thumbnails,
                "image_urls": image_urls
            }
            
            logger.info(f"獲取到 {num_pages} 頁圖片")
            return gallery_data
            
        except Exception as e:
            logger.error(f"獲取畫廊數據失敗: {e}")
            return None
    
    def display_gallery_info(self, gallery_data):
        """顯示畫廊信息"""
        if not gallery_data:
            print("沒有可顯示的畫廊數據")
            return
        
        print("\n" + "="*50)
        print(f"標題: {gallery_data['title']}")
        
        if gallery_data['original_title']:
            print(f"原標題: {gallery_data['original_title']}")
        
        print(f"畫廊ID: {gallery_data['gallery_id']}")
        print(f"頁數: {gallery_data['num_pages']}")
        
        print("\n標籤:")
        for tag in gallery_data['tags']:
            print(f"  - {tag['name']} {tag['count']}")
        
        print("="*50 + "\n")
        
        # 提示用戶選擇操作
        print("可用操作:")
        print("1. 下載並保存為EPUB")
        print("2. 顯示所有圖片URL")
        print("3. 下載並以瀏覽器打開圖片 (需要安裝PIL)")
        print("4. 退出")
    
    def download_image(self, img_url, save_path):
        """下載圖片並保存到指定路徑"""
        try:
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
                    jpg_path = os.path.splitext(save_path)[0] + '.jpg'
                    img.save(jpg_path, 'JPEG')
                    os.remove(save_path)  # 刪除原圖片
                    save_path = jpg_path
            except Exception as e:
                logger.error(f"圖片轉換錯誤: {e}")
            
            return save_path
        except Exception as e:
            logger.error(f"下載圖片失敗 {img_url}: {e}")
            return None
    
    def download_images(self, image_urls, item_dir):
        """批量下載圖片並返回本地路徑列表"""
        downloaded_images = []
        
        for i, img_url in enumerate(image_urls):
            file_ext = os.path.splitext(img_url)[1]
            if not file_ext:
                file_ext = '.jpg'  # 預設擴展名
            
            img_filename = f"image_{i+1:03d}{file_ext}"
            img_path = os.path.join(item_dir, img_filename)
            
            downloaded_path = self.download_image(img_url, img_path)
            if downloaded_path:
                downloaded_images.append(downloaded_path)
                
                # 顯示進度
                if i % 5 == 0 or i == len(image_urls) - 1:
                    logger.info(f"已下載 {i+1}/{len(image_urls)} 張圖片")
        
        return downloaded_images
    
    def create_epub(self, title, image_urls, output_path):
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
        '''
        
        css = epub.EpubItem(
            uid="style_default",
            file_name="style/default.css",
            media_type="text/css",
            content=style
        )
        book.add_item(css)
        
        # 下載圖片
        logger.info("開始下載圖片...")
        downloaded_images = self.download_images(image_urls, self.temp_dir)
        
        # 建立章節並添加圖片
        chapters = []
        
        # 如果有圖片，設置第一張為封面
        if downloaded_images:
            cover_path = downloaded_images[0]
            with open(cover_path, 'rb') as f:
                cover_content = f.read()
            book.set_cover("cover.jpg", cover_content)
        
        for i, img_path in enumerate(downloaded_images):
            chapter = epub.EpubHtml(
                title=f'{i+1}',
                file_name=f'page_{i+1:03d}.xhtml',
                lang='zh-TW'
            )
            
            img_filename = os.path.basename(img_path)
            img_id = f'image_{i+1:03d}'
            
            # 讀取圖片並添加到EPUB
            with open(img_path, 'rb') as f:
                img_content = f.read()
            
            # 判斷圖片類型
            media_type = 'image/jpeg' if img_path.endswith('.jpg') else 'image/png'
            
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
    
    def display_images(self, downloaded_images):
        """顯示下載的圖片"""
        try:
            from PIL import Image
            import tkinter as tk
            from tkinter import ttk
            from PIL import ImageTk
            
            root = tk.Tk()
            root.title("NHentai 瀏覽器")
            root.geometry("1024x768")
            
            # 創建主框架
            main_frame = ttk.Frame(root)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # 創建畫布和滾動條
            canvas = tk.Canvas(main_frame)
            scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
            
            # 配置畫布
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            
            # 放置畫布和滾動條
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # 創建內容框架
            content_frame = ttk.Frame(canvas)
            canvas.create_window((0, 0), window=content_frame, anchor="nw")
            
            # 加載每個圖像並顯示
            photo_references = []  # 保持對圖像的引用，防止垃圾回收
            
            for i, img_path in enumerate(downloaded_images):
                # 創建圖片標籤
                img_label = ttk.Label(content_frame, text=f"圖片 {i+1}")
                img_label.pack(pady=(20, 5))
                
                # 加載圖片
                img = Image.open(img_path)
                
                # 調整圖片大小以適合窗口
                width, height = img.size
                max_width = 900  # 最大寬度
                
                if width > max_width:
                    ratio = max_width / width
                    new_width = max_width
                    new_height = int(height * ratio)
                    img = img.resize((new_width, new_height), Image.LANCZOS)
                
                # 轉換為Tkinter格式並顯示
                photo = ImageTk.PhotoImage(img)
                photo_references.append(photo)  # 保持引用
                
                img_display = ttk.Label(content_frame, image=photo)
                img_display.pack(pady=(0, 20))
                
                # 分隔線
                if i < len(downloaded_images) - 1:
                    separator = ttk.Separator(content_frame, orient=tk.HORIZONTAL)
                    separator.pack(fill=tk.X, padx=20, pady=10)
            
            # 啟動主循環
            root.mainloop()
            
        except ImportError:
            logger.error("無法顯示圖片：缺少必要的庫。請安裝PIL和tkinter。")
            print("無法顯示圖片：缺少必要的庫。請安裝PIL和tkinter。")
            # 顯示路徑，讓用戶可以手動打開
            print(f"圖片已下載到: {self.temp_dir}")
            print("您可以使用檔案瀏覽器手動打開它們。")

def main():
    parser = argparse.ArgumentParser(description='nhentai 瀏覽工具')
    parser.add_argument('url', help='nhentai 畫廊URL (例如 https://nhentai.net/g/123456/)')
    parser.add_argument('-d', '--output-dir', default='output/nh', help='基本輸出目錄 (預設: output/nh)')
    
    args = parser.parse_args()
    
    # 驗證URL格式
    if not re.match(r'https?://nhentai\.net/g/\d+/?', args.url):
        print("錯誤: URL格式不正確。請提供有效的nhentai畫廊URL，例如 https://nhentai.net/g/123456/")
        return
    
    viewer = NHentaiViewer(output_dir=args.output_dir)
    gallery_data = viewer.fetch_gallery_data(args.url)
    
    if not gallery_data:
        print("獲取畫廊數據失敗。請檢查URL和網絡連接。")
        return
    
    viewer.display_gallery_info(gallery_data)
    
    while True:
        choice = input("\n請選擇操作 (1-4): ")
        
        if choice == '1':
            # 建立安全的檔名
            safe_title = re.sub(r'[\\/*?:"<>|]', '', gallery_data['title'])[:100]
            epub_filename = f"{safe_title}.epub"
            output_path = os.path.join(viewer.gallery_dir, epub_filename)
            
            print(f"正在下載圖片並創建EPUB...")
            epub_path = viewer.create_epub(gallery_data['title'], gallery_data['image_urls'], output_path)
            print(f"EPUB已建立: {epub_path}")
            
        elif choice == '2':
            print("\n所有圖片URL:")
            for i, url in enumerate(gallery_data['image_urls']):
                print(f"{i+1}: {url}")
            
        elif choice == '3':
            print("正在下載圖片...")
            downloaded_images = viewer.download_images(gallery_data['image_urls'], viewer.temp_dir)
            if downloaded_images:
                print(f"已下載 {len(downloaded_images)} 張圖片")
                viewer.display_images(downloaded_images)
            else:
                print("下載圖片失敗")
            
        elif choice == '4':
            print("退出程序")
            
            # 清理臨時目錄
            try:
                if os.path.exists(viewer.temp_dir):
                    shutil.rmtree(viewer.temp_dir)
                    logger.debug(f"已清理臨時目錄: {viewer.temp_dir}")
            except Exception as e:
                logger.warning(f"清理臨時目錄失敗: {e}")
            
            break
            
        else:
            print("無效的選擇，請輸入1-4之間的數字")


if __name__ == "__main__":
    main()
