#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import requests
import re
import argparse
import json
import logging
from bs4 import BeautifulSoup
import datetime
from ebooklib import epub
import uuid

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("nhentai_info_viewer.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class NHentaiInfoViewer:
    def __init__(self, output_dir='output/nh_info'):
        self.output_dir = output_dir
        
        # 確保資料夾存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        logger.info(f"初始化完成，輸出目錄: {self.output_dir}")
    
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
            
            # 提取頁數
            num_pages_pattern = r'"num_pages":\s*(\d+)'
            num_pages_match = re.search(num_pages_pattern, response.text)
            num_pages = int(num_pages_match.group(1)) if num_pages_match else 0
            
            # 獲取上傳時間
            upload_date_pattern = r'"upload_date":\s*(\d+)'
            upload_date_match = re.search(upload_date_pattern, response.text)
            upload_timestamp = int(upload_date_match.group(1)) if upload_date_match else 0
            upload_date = datetime.datetime.fromtimestamp(upload_timestamp).strftime('%Y-%m-%d %H:%M:%S') if upload_timestamp else "未知日期"
            
            # 獲取標籤
            tags = []
            tag_elements = soup.select('#tags .tag')
            for tag_element in tag_elements:
                tag_name_element = tag_element.select_one('.name')
                tag_count_element = tag_element.select_one('.count')
                tag_type_element = tag_element.select_one('.tag-container')
                
                if tag_name_element:
                    tag_name = tag_name_element.text.strip()
                    tag_count = tag_count_element.text.strip() if tag_count_element else ""
                    tag_type = ""
                    
                    if tag_type_element and 'data-tag' in tag_type_element.attrs:
                        tag_classes = tag_type_element.get('class', [])
                        for cls in tag_classes:
                            if cls.startswith('tag-container-'):
                                tag_type = cls.replace('tag-container-', '')
                                break
                    
                    tags.append({"name": tag_name, "count": tag_count, "type": tag_type})
            
            # 將標籤按類型分類
            categorized_tags = {}
            for tag in tags:
                tag_type = tag.get('type', 'other')
                if tag_type not in categorized_tags:
                    categorized_tags[tag_type] = []
                categorized_tags[tag_type].append(tag)
            
            # 獲取縮圖URL
            cover_url = ""
            cover_element = soup.select_one('#cover img')
            if cover_element and 'data-src' in cover_element.attrs:
                cover_url = cover_element['data-src']
            elif cover_element and 'src' in cover_element.attrs:
                cover_url = cover_element['src']
            
            # 返回收集的數據
            gallery_data = {
                "title": title,
                "original_title": original_title,
                "gallery_id": gallery_id,
                "media_id": media_id,
                "num_pages": num_pages,
                "upload_date": upload_date,
                "tags": tags,
                "categorized_tags": categorized_tags,
                "cover_url": cover_url,
                "url": url
            }
            
            logger.info(f"獲取到 {title} - {num_pages} 頁")
            return gallery_data
            
        except Exception as e:
            logger.error(f"獲取畫廊數據失敗: {e}")
            return None
    
    def display_gallery_info(self, gallery_data):
        """顯示畫廊信息"""
        if not gallery_data:
            print("沒有可顯示的畫廊數據")
            return
        
        print("\n" + "="*80)
        print(f"標題: {gallery_data['title']}")
        
        if gallery_data['original_title']:
            print(f"原標題: {gallery_data['original_title']}")
        
        print(f"畫廊ID: {gallery_data['gallery_id']}")
        print(f"頁數: {gallery_data['num_pages']}")
        print(f"上傳日期: {gallery_data['upload_date']}")
        print(f"URL: {gallery_data['url']}")
        
        # 顯示分類後的標籤
        categorized_tags = gallery_data.get('categorized_tags', {})
        if categorized_tags:
            print("\n標籤分類:")
            
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
            
            # 按類型顯示標籤
            for tag_type, tags in categorized_tags.items():
                tag_type_display = tag_type_names.get(tag_type, tag_type)
                print(f"\n{tag_type_display}:")
                for tag in tags:
                    print(f"  - {tag['name']} {tag['count']}")
        else:
            # 如果沒有分類標籤，則顯示所有標籤
            print("\n標籤:")
            for tag in gallery_data['tags']:
                print(f"  - {tag['name']} {tag['count']}")
        
        print("="*80 + "\n")
    
    def save_info_to_json(self, gallery_data, filename=None):
        """保存畫廊信息為JSON文件"""
        if not gallery_data:
            print("沒有可保存的畫廊數據")
            return None
        
        # 如果未提供文件名，則使用畫廊標題作為文件名
        if not filename:
            # 建立安全的檔名
            safe_title = re.sub(r'[\\/*?:"<>|]', '', gallery_data['title'])[:100]
            filename = f"{safe_title}.json"
        
        output_path = os.path.join(self.output_dir, filename)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(gallery_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已保存畫廊信息到: {output_path}")
            print(f"已保存畫廊信息到: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"保存畫廊信息失敗: {e}")
            print(f"保存畫廊信息失敗: {e}")
            return None
    
    def search_content(self, gallery_data, keyword):
        """搜索畫廊內容中包含指定關鍵詞的標籤"""
        if not gallery_data:
            print("沒有可搜索的畫廊數據")
            return []
        
        results = []
        
        # 搜索標題
        if keyword.lower() in gallery_data['title'].lower():
            results.append(("標題", gallery_data['title']))
        
        # 搜索原標題
        if gallery_data['original_title'] and keyword.lower() in gallery_data['original_title'].lower():
            results.append(("原標題", gallery_data['original_title']))
        
        # 搜索標籤
        for tag in gallery_data['tags']:
            # 移除標籤後的計數部分（例如 "big breasts 182K" 變為 "big breasts"）
            tag_name_only = tag['name'].split(' ')[0] if ' ' in tag['name'] and tag['name'].split(' ')[1].strip().lower().endswith(('k', 'k+')) else tag['name']
            if keyword.lower() in tag_name_only.lower():
                results.append(("標籤", tag_name_only))
        
        return results

    def create_tags_epub(self, gallery_data, filename=None):
        """創建只包含標籤信息的EPUB文件"""
        if not gallery_data:
            print("沒有可用的畫廊數據來創建EPUB")
            return None
        
        # 如果未提供文件名，則使用畫廊標題作為文件名
        if not filename:
            # 建立安全的檔名
            safe_title = re.sub(r'[\\/*?:"<>|]', '', gallery_data['title'])[:100]
            filename = f"{safe_title}_tags.epub"
        
        output_path = os.path.join(self.output_dir, filename)
        
        try:
            # 創建EPUB檔案
            book = epub.EpubBook()
            
            # 設置元數據
            book.set_identifier(str(uuid.uuid4()))
            book.set_title(f"{gallery_data['title']} - 標籤信息")
            book.set_language('zh-TW')
            
            # 添加樣式
            style = '''
            @namespace epub "http://www.idpf.org/2007/ops";
            body {
                font-family: sans-serif;
                margin: 2em;
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
            }
            .tag {
                display: inline-block;
                background-color: #f0f0f0;
                padding: 5px 10px;
                margin: 5px;
                border-radius: 3px;
            }
            .info {
                margin: 1em 0;
            }
            .info span {
                font-weight: bold;
            }
            '''
            
            css = epub.EpubItem(
                uid="style_default",
                file_name="style/default.css",
                media_type="text/css",
                content=style
            )
            book.add_item(css)
            
            # 創建主要內容
            content = f'''
            <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
            <head>
                <title>{gallery_data['title']} - 標籤信息</title>
                <link rel="stylesheet" type="text/css" href="style/default.css" />
            </head>
            <body>
                <h1>{gallery_data['title']}</h1>
            '''
            
            # 添加原標題(如果有)
            if gallery_data['original_title']:
                content += f'<div class="info"><span>原標題:</span> {gallery_data["original_title"]}</div>'
            
            # 添加基本信息
            content += f'''
                <div class="info"><span>畫廊ID:</span> {gallery_data['gallery_id']}</div>
                <div class="info"><span>頁數:</span> {gallery_data['num_pages']}</div>
                <div class="info"><span>上傳日期:</span> {gallery_data['upload_date']}</div>
                <div class="info"><span>URL:</span> <a href="{gallery_data['url']}">{gallery_data['url']}</a></div>
            '''
            
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
            categorized_tags = gallery_data.get('categorized_tags', {})
            for tag_type, tags in categorized_tags.items():
                tag_type_display = tag_type_names.get(tag_type, tag_type)                
                content += f'<h2>{tag_type_display}</h2>\n<div>'
                
                for tag in tags:
                    # 移除標籤後的數字部分（例如 "big breasts 182K" 變為 "big breasts"）
                    tag_name = tag['name'].split(' ')[0] if ' ' in tag['name'] and tag['name'].split(' ')[1].strip().lower().endswith(('k', 'k+')) else tag['name']
                    content += f'<div class="tag">{tag_name}</div>'
                
                content += '</div>'
            
            content += '''
            </body>
            </html>
            '''
            
            # 創建章節
            chapter = epub.EpubHtml(
                title=f'標籤信息',
                file_name='tags.xhtml',
                lang='zh-TW',
                content=content
            )
            chapter.add_item(css)
            book.add_item(chapter)
            
            # 添加目錄和導航
            book.toc = [chapter]
            book.spine = ['nav', chapter]
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            
            # 寫入檔案
            epub.write_epub(output_path, book, {})
            logger.info(f"已建立標籤EPUB: {output_path}")
            print(f"已建立標籤EPUB: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"創建標籤EPUB失敗: {e}")
            print(f"創建標籤EPUB失敗: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description='nhentai 信息瀏覽工具')
    parser.add_argument('url', help='nhentai 畫廊URL (例如 https://nhentai.net/g/123456/)')
    parser.add_argument('-d', '--output-dir', default='output/nh_info', help='輸出目錄 (預設: output/nh_info)')
    parser.add_argument('-s', '--save', action='store_true', help='自動保存信息為JSON文件')
    parser.add_argument('-q', '--quiet', action='store_true', help='安靜模式，僅顯示最基本信息')
    parser.add_argument('-e', '--create-epub', action='store_true', help='自動創建標籤EPUB文件')
    
    args = parser.parse_args()
    
    # 驗證URL格式
    if not re.match(r'https?://nhentai\.net/g/\d+/?', args.url):
        print("錯誤: URL格式不正確。請提供有效的nhentai畫廊URL，例如 https://nhentai.net/g/123456/")
        return
    
    viewer = NHentaiInfoViewer(output_dir=args.output_dir)
    gallery_data = viewer.fetch_gallery_data(args.url)
    
    if not gallery_data:
        print("獲取畫廊數據失敗。請檢查URL和網絡連接。")
        return
    
    # 在安靜模式下僅顯示基本信息
    if args.quiet:
        print(f"標題: {gallery_data['title']}")
        print(f"頁數: {gallery_data['num_pages']}")
        print(f"URL: {gallery_data['url']}")
    else:
        viewer.display_gallery_info(gallery_data)
    
    # 如果指定了保存選項，則自動保存為JSON
    if args.save:
        viewer.save_info_to_json(gallery_data)
    
    # 如果指定了創建EPUB選項，則自動創建標籤EPUB
    if args.create_epub:
        viewer.create_tags_epub(gallery_data)
    
    # 互動模式
    if not args.quiet:
        while True:
            print("\n可用操作:")
            print("1. 保存信息為JSON")
            print("2. 搜索關鍵詞")
            print("3. 展示詳細標籤")
            print("4. 創建標籤EPUB")
            print("5. 退出")
            
            choice = input("\n請選擇操作 (1-5): ")
            
            if choice == '1':
                viewer.save_info_to_json(gallery_data)
                
            elif choice == '2':
                keyword = input("請輸入要搜索的關鍵詞: ")
                results = viewer.search_content(gallery_data, keyword)
                
                if results:
                    print(f"\n找到 {len(results)} 個匹配項:")
                    for category, value in results:
                        print(f"  - {category}: {value}")
                else:
                    print("\n未找到匹配項")
                
            elif choice == '3':
                # 按類型顯示所有標籤
                categorized_tags = gallery_data.get('categorized_tags', {})
                
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
                
                print("\n詳細標籤列表:")
                for tag_type, tags in categorized_tags.items():
                    tag_type_display = tag_type_names.get(tag_type, tag_type)
                    print(f"\n{tag_type_display}:")
                    for tag in tags:
                        print(f"  - {tag['name']} {tag['count']}")
            
            elif choice == '4':
                # 創建標籤EPUB
                print("正在創建僅包含標籤信息的EPUB...")
                viewer.create_tags_epub(gallery_data)
                
            elif choice == '5':
                print("退出程序")
                break
                
            else:
                print("無效的選擇，請輸入1-5之間的數字")


if __name__ == "__main__":
    main()
