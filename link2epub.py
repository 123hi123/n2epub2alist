#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
import datetime
import feedparser
import requests
from bs4 import BeautifulSoup
from ebooklib import epub
from PIL import Image
from io import BytesIO
import argparse
import re
import uuid
import shutil
import numpy as np
import cv2
import xml.etree.ElementTree as ET

class OPMLParser:
    def __init__(self):
        pass
        
    def parse(self, opml_file):
        """解析OPML文件並返回其中所有的RSS URL"""
        try:
            tree = ET.parse(opml_file)
            root = tree.getroot()
            
            # 找到所有的 outline 元素
            rss_urls = []
            
            # 在body中尋找所有outline元素
            body = root.find('body')
            if body is None:
                print("OPML文件沒有body元素")
                return []
                
            # 搜尋所有outline元素
            for outline in body.findall('.//outline'):
                # 檢查是否有xmlUrl屬性 (RSS URL)
                xml_url = outline.get('xmlUrl')
                if xml_url:
                    title = outline.get('title') or outline.get('text') or "未命名"
                    rss_urls.append({
                        'title': title,
                        'url': xml_url
                    })
            
            print(f"從OPML文件中找到 {len(rss_urls)} 個RSS來源")
            return rss_urls
        except Exception as e:
            print(f"解析OPML文件時出錯: {e}")
            return []

class RSStoEPUB:
    def __init__(self, rss_url, output_dir='book/nh', temp_dir='temp', skip_pages=True, auto_merge=True):
        self.rss_url = rss_url
        self.output_dir = output_dir
        self.temp_dir = temp_dir
        self.skip_pages = skip_pages  # 是否跳過目錄頁
        self.auto_merge = auto_merge  # 是否自動合併所有條目為一個EPUB
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 建立輸出目錄
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

    def parse_rss(self):
        """解析 RSS 內容"""
        print(f"解析 RSS: {self.rss_url}")
        feed = feedparser.parse(self.rss_url)
        
        if not feed.entries:
            print("未找到 RSS 條目")
            return []
        
        print(f"找到 {len(feed.entries)} 個條目")
        return feed.entries

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
                    img.save(save_path.replace('.webp', '.jpg'), 'JPEG')
                    os.remove(save_path)  # 刪除原圖片
                    save_path = save_path.replace('.webp', '.jpg')
            except Exception as e:
                print(f"圖片轉換錯誤: {e}")
            
            return save_path
        except Exception as e:
            print(f"下載圖片失敗 {img_url}: {e}")
            return None

    def is_index_page(self, img_path):
        """檢測圖片是否為頁碼頁（如顯示目錄或頁碼的頁面）"""
        if not self.skip_pages:
            return False
            
        try:
            # 讀取圖片
            img = cv2.imread(img_path)
            if img is None:
                return False
                
            # 檢查是否為黑色背景
            is_dark_bg = np.mean(img) < 50
            
            # 檢查是否包含數字列表模式
            # 轉為灰度並進行文本檢測
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV if is_dark_bg else cv2.THRESH_BINARY)
            
            # 檢查是否有規律的數字模式
            # 簡單檢測：檢查是否有多個小區域按順序排列
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 如果有多個（比如超過5個）小而規律的輪廓，可能是頁碼頁
            small_contours = [c for c in contours if 100 < cv2.contourArea(c) < 10000]
            
            if len(small_contours) > 5:
                # 檢查這些輪廓是否按垂直方向排列
                centers = [np.mean(c, axis=0)[0] for c in small_contours]
                y_coords = sorted([c[1] for c in centers])
                
                # 檢查是否有規律的垂直間隔
                if len(y_coords) > 5:
                    diffs = [y_coords[i+1] - y_coords[i] for i in range(len(y_coords)-1)]
                    avg_diff = np.mean(diffs)
                    std_diff = np.std(diffs)
                    
                    # 如果間隔很規律（標準差小），可能是頁碼頁
                    if std_diff < avg_diff * 0.3 and is_dark_bg:
                        return True
                        
            return False
            
        except Exception as e:
            print(f"檢測頁碼頁時出錯: {e}")
            return False

    def extract_images(self, html_content, item_dir):
        """從 HTML 中提取圖片 URL 並下載"""
        soup = BeautifulSoup(html_content, 'lxml')
        img_tags = soup.find_all('img')
        
        images = []
        for i, img in enumerate(img_tags):
            if 'src' in img.attrs:
                img_url = img['src']
                file_ext = os.path.splitext(img_url)[1]
                if not file_ext:
                    file_ext = '.webp'  # 預設擴展名
                
                img_filename = f"image_{i+1:03d}{file_ext}"
                img_path = os.path.join(item_dir, img_filename)
                
                downloaded_path = self.download_image(img_url, img_path)
                if downloaded_path:
                    # 檢查是否為頁碼頁
                    if not self.is_index_page(downloaded_path):
                        images.append(downloaded_path)
                    else:
                        print(f"跳過頁碼頁: {img_filename}")
                        os.remove(downloaded_path)  # 刪除頁碼頁
                    
                    # 顯示進度
                    if i % 5 == 0:
                        print(f"已下載 {i+1}/{len(img_tags)} 張圖片")
        
        return images

    def create_epub(self, title, images, output_path):
        """建立 EPUB 檔案"""
        book = epub.EpubBook()
        
        # 設置元數據
        book.set_identifier(str(uuid.uuid4()))
        book.set_title(title)
        book.set_language('zh-TW')
        
        # 添加封面
        if images:
            cover_path = images[0]
            with open(cover_path, 'rb') as f:
                cover_content = f.read()
            book.set_cover("cover.jpg", cover_content)
        
        # 添加樣式
        style = '''
        @namespace epub "http://www.idpf.org/2007/ops";
        body {
            font-family: sans-serif;
            text-align: center;
        }
        img {
            max-width: 100%;
            max-height: 100vh;
            display: block;
            margin: 0 auto;
        }
        '''
        
        css = epub.EpubItem(
            uid="style_default",
            file_name="style/default.css",
            media_type="text/css",
            content=style
        )
        book.add_item(css)
        
        # 建立章節並添加圖片
        chapters = []
        for i, img_path in enumerate(images):
            chapter = epub.EpubHtml(
                title=f'Page {i+1}',
                file_name=f'page_{i+1:03d}.xhtml',
                lang='zh-TW'
            )
            
            # 獲取圖片檔名
            img_filename = os.path.basename(img_path)
            img_id = f'image_{i+1:03d}'
            
            # 讀取圖片內容
            with open(img_path, 'rb') as f:
                img_content = f.read()
            
            # 添加圖片到 EPUB
            img_item = epub.EpubItem(
                uid=img_id,
                file_name=f'images/{img_filename}',
                media_type=f'image/{"jpeg" if img_path.endswith(".jpg") else "webp"}',
                content=img_content
            )
            book.add_item(img_item)
            
            # 在章節中引用圖片
            chapter.content = f'''
            <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
            <head>
                <title>{title} - Page {i+1}</title>
                <link rel="stylesheet" type="text/css" href="style/default.css" />
            </head>
            <body>
                <img src="images/{img_filename}" alt="Page {i+1}" />
            </body>
            </html>
            '''
            
            chapter.add_item(css)
            book.add_item(chapter)
            chapters.append(chapter)
        
        # 添加目錄
        book.toc = chapters
        
        # 添加 spine
        book.spine = ['nav'] + chapters
        
        # 添加 NCX 和導航
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # 寫入檔案
        epub.write_epub(output_path, book, {})
        return output_path

    def process_item(self, item):
        """處理單個 RSS 條目，下載圖片但不立即生成 EPUB"""
        title = item.title
        # 清理標題，使其適合作為檔名
        safe_title = re.sub(r'[\\/*?:"<>|]', '', title)[:100]
        
        print(f"\n處理: {safe_title}")
        
        # 創建臨時目錄
        item_dir = os.path.join(self.temp_dir, str(uuid.uuid4()))
        os.makedirs(item_dir, exist_ok=True)
        
        try:
            # 提取和下載圖片
            images = self.extract_images(item.description, item_dir)
            
            if not images:
                print(f"未找到圖片: {safe_title}")
                return None
            
            print(f"共下載 {len(images)} 張圖片")
            
            # 返回標題和圖片列表，不立即生成 EPUB
            return {
                'title': title,
                'images': images,
                'temp_dir': item_dir
            }
        
        except Exception as e:
            print(f"處理項目時出錯: {e}")
            # 清理臨時目錄
            if os.path.exists(item_dir):
                shutil.rmtree(item_dir)
            return None

    def create_merged_epub(self, items_data):
        """合併多個 RSS 條目為一個 EPUB"""
        if not items_data:
            print("沒有可合併的條目")
            return None
        
        # 使用當前時間作為檔名
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        output_filename = f"{timestamp}.epub"
        output_path = os.path.join(self.output_dir, output_filename)
        
        # 創建 EPUB 書籍
        book = epub.EpubBook()
        book.set_identifier(str(uuid.uuid4()))
        book.set_title(f"RSS 合集 {timestamp}")
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
            max-height: 100vh;
            display: block;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            font-size: 1.5em;
            margin: 1em 0;
        }
        section {
            page-break-before: always;
        }
        '''
        
        css = epub.EpubItem(
            uid="style_default",
            file_name="style/default.css",
            media_type="text/css",
            content=style
        )
        book.add_item(css)
        
        # 封面章節
        cover_chapter = epub.EpubHtml(
            title='封面',
            file_name='cover.xhtml',
            lang='zh-TW'
        )
        cover_chapter.content = f'''
        <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
        <head>
            <title>封面</title>
            <link rel="stylesheet" type="text/css" href="style/default.css" />
        </head>
        <body>
            <h1>RSS 合集 {timestamp}</h1>
            <p>生成時間: {now.strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>包含 {len(items_data)} 個條目</p>
        </body>
        </html>
        '''
        cover_chapter.add_item(css)
        book.add_item(cover_chapter)
        
        # 目錄章節
        toc_chapter = epub.EpubHtml(
            title='目錄',
            file_name='toc.xhtml',
            lang='zh-TW'
        )
        
        toc_content = f'''
        <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
        <head>
            <title>目錄</title>
            <link rel="stylesheet" type="text/css" href="style/default.css" />
        </head>
        <body>
            <h1>目錄</h1>
            <ul>
        '''
        
        for i, item in enumerate(items_data):
            toc_content += f'<li><a href="item_{i+1:03d}_title.xhtml">{item["title"]}</a></li>\n'
        
        toc_content += '''
            </ul>
        </body>
        </html>
        '''
        
        toc_chapter.content = toc_content
        toc_chapter.add_item(css)
        book.add_item(toc_chapter)
        
        # 所有章節列表
        chapters = [cover_chapter, toc_chapter]
        toc_entries = []
        
        # 如果第一個條目有圖片，使用其第一張圖片作為封面
        if items_data and items_data[0]['images']:
            cover_path = items_data[0]['images'][0]
            with open(cover_path, 'rb') as f:
                cover_content = f.read()
            book.set_cover("cover.jpg", cover_content)
        
        # 處理每個條目
        image_counter = 0
        for i, item_data in enumerate(items_data):
            title = item_data['title']
            images = item_data['images']
            
            # 添加條目標題章節
            title_chapter = epub.EpubHtml(
                title=title,
                file_name=f'item_{i+1:03d}_title.xhtml',
                lang='zh-TW'
            )
            title_chapter.content = f'''
            <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
            <head>
                <title>{title}</title>
                <link rel="stylesheet" type="text/css" href="style/default.css" />
            </head>
            <body>
                <h1>{title}</h1>
            </body>
            </html>
            '''
            title_chapter.add_item(css)
            book.add_item(title_chapter)
            chapters.append(title_chapter)
            
            # 為每個條目創建目錄條目
            section_chapters = [title_chapter]
            
            # 添加條目的所有圖片
            for j, img_path in enumerate(images):
                image_counter += 1
                img_filename = os.path.basename(img_path)
                img_id = f'image_{image_counter:04d}'
                chapter_id = f'item_{i+1:03d}_page_{j+1:03d}'
                
                # 讀取圖片內容
                with open(img_path, 'rb') as f:
                    img_content = f.read()
                
                # 添加圖片到 EPUB
                img_item = epub.EpubItem(
                    uid=img_id,
                    file_name=f'images/{img_id}_{img_filename}',
                    media_type=f'image/{"jpeg" if img_path.endswith(".jpg") else "webp"}',
                    content=img_content
                )
                book.add_item(img_item)
                
                # 創建章節
                chapter = epub.EpubHtml(
                    title=f'{title} - {j+1}',
                    file_name=f'{chapter_id}.xhtml',
                    lang='zh-TW'
                )
                
                # 在章節中引用圖片
                chapter.content = f'''
                <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
                <head>
                    <title>{title} - {j+1}</title>
                    <link rel="stylesheet" type="text/css" href="style/default.css" />
                </head>
                <body>
                    <img src="images/{img_id}_{img_filename}" alt="{title} - {j+1}" />
                </body>
                </html>
                '''
                
                chapter.add_item(css)
                book.add_item(chapter)
                chapters.append(chapter)
                section_chapters.append(chapter)
            
            # 添加此條目到目錄
            toc_entries.append((title, section_chapters))
        
        # 創建階層式目錄
        book.toc = [(epub.Section('封面'), [cover_chapter, toc_chapter])]
        for title, section_chapters in toc_entries:
            book.toc.append((epub.Section(title), section_chapters))
        
        # 添加 spine
        book.spine = chapters
        
        # 添加 NCX 和導航
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # 寫入檔案
        epub.write_epub(output_path, book, {})
        print(f"已合併 EPUB: {output_path}")
        
        return output_path

    def process_all(self):
        """處理所有 RSS 條目"""
        entries = self.parse_rss()
        if not entries:
            return
        
        items_data = []
        try:
            for i, item in enumerate(entries):
                print(f"\n處理項目 {i+1}/{len(entries)}")
                result = self.process_item(item)
                if result:
                    items_data.append(result)
            
            if items_data:
                if self.auto_merge:
                    # 合併為一個 EPUB
                    merged_epub = self.create_merged_epub(items_data)
                    print(f"\n完成! 已合併為一個 EPUB 檔案: {merged_epub}")
                else:
                    # 創建單獨的 EPUB
                    results = []
                    for item_data in items_data:
                        title = item_data['title']
                        images = item_data['images']
                        safe_title = re.sub(r'[\\/*?:"<>|]', '', title)[:100]
                        output_path = os.path.join(self.output_dir, f"{safe_title}.epub")
                        result = self.create_epub(title, images, output_path)
                        if result:
                            results.append(result)
                    
                    print(f"\n完成! 已建立 {len(results)} 個 EPUB 檔案")
                    for path in results:
                        print(f"- {path}")
        finally:
            # 清理所有臨時目錄
            for item_data in items_data:
                temp_dir = item_data.get('temp_dir')
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)


def process_opml(opml_file, output_dir='book/nh', temp_dir='temp', skip_pages=True, auto_merge=True):
    """處理OPML文件，下載所有RSS並生成EPUB"""
    parser = OPMLParser()
    rss_feeds = parser.parse(opml_file)
    
    if not rss_feeds:
        print("OPML文件中未找到RSS訂閱")
        return []
    
    results = []
    all_items_data = []
    
    try:
        for i, feed in enumerate(rss_feeds):
            print(f"\n處理RSS訂閱 {i+1}/{len(rss_feeds)}: {feed['title']}")
            converter = RSStoEPUB(feed['url'], output_dir, temp_dir, skip_pages, False)  # 不自動合併
            
            # 解析RSS條目
            entries = converter.parse_rss()
            if not entries:
                continue
            
            # 處理所有條目並收集數據
            items_data = []
            for j, item in enumerate(entries):
                print(f"處理項目 {j+1}/{len(entries)}")
                result = converter.process_item(item)
                if result:
                    result['feed_title'] = feed['title']  # 添加來源標題
                    items_data.append(result)
                    all_items_data.append(result)
            
            # 如果不自動合併所有訂閱，則每個訂閱生成一個EPUB
            if not auto_merge and items_data:
                # 使用訂閱名稱作為文件名
                safe_title = re.sub(r'[\\/*?:"<>|]', '', feed['title'])[:100]
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"{safe_title}_{timestamp}.epub"
                output_path = os.path.join(output_dir, output_filename)
                
                # 創建一個合併的EPUB
                merged = converter.create_merged_epub(items_data)
                if merged:
                    results.append(merged)
    
    finally:
        # 清理所有臨時目錄
        for item_data in all_items_data:
            temp_dir = item_data.get('temp_dir')
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    
    # 如果需要合併所有訂閱為一個文件
    if auto_merge and all_items_data:
        # 創建一個新的RSStoEPUB對象來合併所有內容
        merger = RSStoEPUB("", output_dir, temp_dir, skip_pages, auto_merge)
        merged_all = merger.create_merged_epub(all_items_data)
        if merged_all:
            results = [merged_all]
    
    if results:
        print(f"\n完成! 已創建 {len(results)} 個 EPUB 文件")
        for path in results:
            print(f"- {path}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description='將 RSS 網址或 OPML 文件轉換為 EPUB')
    
    # 創建子命令
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # RSS 命令
    rss_parser = subparsers.add_parser('rss', help='處理單個RSS')
    rss_parser.add_argument('url', help='RSS 網址')
    rss_parser.add_argument('-o', '--output', default='book/nh', help='輸出目錄 (預設: book/nh)')
    rss_parser.add_argument('-t', '--temp', default='temp', help='臨時目錄 (預設: temp)')
    rss_parser.add_argument('--no-skip', action='store_false', dest='skip_pages', 
                           help='不跳過目錄頁')
    rss_parser.add_argument('--no-merge', action='store_false', dest='auto_merge',
                           help='不要合併為單一EPUB (默認合併)')
    
    # OPML 命令
    opml_parser = subparsers.add_parser('opml', help='處理OPML文件')
    opml_parser.add_argument('file', help='OPML 文件路徑')
    opml_parser.add_argument('-o', '--output', default='book/nh', help='輸出目錄 (預設: book/nh)')
    opml_parser.add_argument('-t', '--temp', default='temp', help='臨時目錄 (預設: temp)')
    opml_parser.add_argument('--no-skip', action='store_false', dest='skip_pages', 
                            help='不跳過目錄頁')
    opml_parser.add_argument('--no-merge', action='store_false', dest='auto_merge',
                            help='不要合併為單一EPUB (默認合併所有訂閱為一個文件)')
    
    args = parser.parse_args()
    
    # 如果沒有提供子命令，顯示幫助
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # 處理 RSS
    if args.command == 'rss':
        converter = RSStoEPUB(args.url, args.output, args.temp, args.skip_pages, args.auto_merge)
        converter.process_all()
    
    # 處理 OPML
    elif args.command == 'opml':
        process_opml(args.file, args.output, args.temp, args.skip_pages, args.auto_merge)


if __name__ == "__main__":
    main() 