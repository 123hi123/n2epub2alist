#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import xml.etree.ElementTree as ET
import urllib.parse
import argparse

class NhentaiRssManager:
    def __init__(self, opml_file='nhentai_rss.opml'):
        self.opml_file = opml_file
        self.base_url = "https://rsshub.comalot.me/nhentai/search/"
        self.html_base = "https://nhentai.net/search/?q="
        self.api_key = "donotusemyvps*thanks"
        
        # 標籤映射表
        self.tag_mapping = {
            'CH': 'chinese',         # 中文
            'FF': 'fullcolor',       # 全彩
            'FC': 'full color',      # 全彩（空格寫法）
            'UC': 'uncensored',      # 無修正
            'LO': 'loli',            # 蘿莉
            'BB': 'big breasts',     # 巨乳
            'C105': 'c105',          # C105（同人展）
            'C104': 'c104',          # C104
            'C103': 'c103',          # C103
            'K': 'karory',           # 畫師Karory
            'D': 'dokuneko-noil',    # 畫師dokuneko-noil
            'K8': 'k8on'             # 畫師k8on
        }

    def load_opml(self):
        """載入OPML文件"""
        try:
            tree = ET.parse(self.opml_file)
            return tree
        except FileNotFoundError:
            # 如果文件不存在，創建一個新的OPML文件結構
            root = ET.Element('opml')
            root.set('version', '1.0')
            
            head = ET.SubElement(root, 'head')
            title = ET.SubElement(head, 'title')
            title.text = 'nhentai RSS源'
            
            body = ET.SubElement(root, 'body')
            
            tree = ET.ElementTree(root)
            return tree
        except Exception as e:
            print(f"載入OPML文件出錯: {e}")
            sys.exit(1)

    def save_opml(self, tree):
        """保存OPML文件"""
        try:
            tree.write(self.opml_file, encoding='utf-8', xml_declaration=True)
            print(f"已成功保存到 {self.opml_file}")
        except Exception as e:
            print(f"保存OPML文件出錯: {e}")
            sys.exit(1)

    def parse_tags(self, tag_input):
        """解析標籤輸入並轉換為搜索字符串"""
        tags = []
        
        # 分割輸入，支持+和空格作為分隔符
        parts = tag_input.replace('+', ' ').split()
        
        for part in parts:
            if part in self.tag_mapping:
                tags.append(self.tag_mapping[part])
            elif part.startswith('-') and part[1:] in self.tag_mapping:
                # 處理排除標籤（如 -FF 表示 -fullcolor）
                tags.append(f"-{self.tag_mapping[part[1:]]}")
            else:
                # 如果不在映射表中，直接使用原標籤
                tags.append(part)
        
        return '+'.join(tags)

    def build_rss_url(self, search_terms):
        """構建RSS URL"""
        # 對搜索詞進行URL編碼
        encoded_terms = urllib.parse.quote(search_terms)
        return f"{self.base_url}{encoded_terms}/detail?key={self.api_key}"

    def build_html_url(self, search_terms):
        """構建HTML URL（網頁搜索URL）"""
        encoded_terms = urllib.parse.quote(search_terms)
        return f"{self.html_base}{encoded_terms}"

    def add_rss(self, tag_input):
        """添加新的RSS連結到OPML文件"""
        # 解析標籤輸入
        search_terms = self.parse_tags(tag_input)
        if not search_terms:
            print("無效的標籤組合")
            return False
        
        # 構建URL
        rss_url = self.build_rss_url(search_terms)
        html_url = self.build_html_url(search_terms)
        
        # 載入OPML文件
        tree = self.load_opml()
        root = tree.getroot()
        
        # 檢查是否已存在相同的RSS
        body = root.find('body')
        if body is None:
            body = ET.SubElement(root, 'body')
        
        for outline in body.findall('.//outline'):
            if outline.get('xmlUrl') == rss_url:
                print(f"RSS已存在: {search_terms}")
                return False
        
        # 創建新的outline元素
        title = f"nhentai - search - {search_terms}"
        outline = ET.SubElement(body, 'outline')
        outline.set('text', title)
        outline.set('title', title)
        outline.set('xmlUrl', rss_url)
        outline.set('htmlUrl', html_url)
        outline.set('type', 'rss')
        
        # 保存文件
        self.save_opml(tree)
        print(f"已添加新RSS: {title}")
        print(f"搜索詞: {search_terms}")
        print(f"RSS URL: {rss_url}")
        
        return True

    def list_rss(self):
        """列出所有RSS連結"""
        tree = self.load_opml()
        root = tree.getroot()
        body = root.find('body')
        
        if body is None:
            print("OPML文件無內容")
            return []
        
        outlines = body.findall('.//outline')
        if not outlines:
            print("沒有找到RSS訂閱")
            return []
        
        print(f"共有 {len(outlines)} 個RSS訂閱:")
        for i, outline in enumerate(outlines, 1):
            title = outline.get('title', '未命名')
            xml_url = outline.get('xmlUrl', '無URL')
            print(f"{i}. {title}")
            print(f"   URL: {xml_url}")
            print()
        
        return outlines

    def delete_rss(self, interactive=True):
        """刪除RSS連結"""
        # 載入OPML文件
        tree = self.load_opml()
        root = tree.getroot()
        body = root.find('body')
        
        if body is None:
            print("OPML文件無內容，無需刪除")
            return False
        
        # 列出所有RSS項目
        outlines = self.list_rss()
        if not outlines:
            return False
        
        if interactive:
            # 互動式刪除
            while True:
                try:
                    choice = input("\n請輸入要刪除的RSS編號 (輸入q退出): ")
                    if choice.lower() == 'q':
                        print("取消刪除操作")
                        return False
                    
                    index = int(choice) - 1
                    if 0 <= index < len(outlines):
                        # 找到要刪除的項目
                        outline_to_delete = outlines[index]
                        title = outline_to_delete.get('title', '未命名')
                        
                        # 確認刪除
                        confirm = input(f"確認刪除 '{title}' ? (y/n): ")
                        if confirm.lower() == 'y':
                            body.remove(outline_to_delete)
                            self.save_opml(tree)
                            print(f"已刪除: {title}")
                            return True
                        else:
                            print("取消刪除")
                    else:
                        print(f"無效的編號，請輸入1-{len(outlines)}之間的數字")
                except ValueError:
                    print("請輸入有效的數字")
                except Exception as e:
                    print(f"刪除操作出錯: {e}")
                    return False
        else:
            # 非互動式刪除（暫時未實現，保留接口）
            print("非互動式刪除功能暫未實現")
            return False

def main():
    parser = argparse.ArgumentParser(description='nhentai RSS管理工具')
    parser.add_argument('-f', '--file', default='nhentai_rss.opml', help='OPML文件路徑 (預設: nhentai_rss.opml)')
    parser.add_argument('-a', '--add', help='添加新的RSS連結 (例如: CH+FF+UC)')
    parser.add_argument('-l', '--list', action='store_true', help='列出所有RSS連結')
    parser.add_argument('-d', '--delete', action='store_true', help='刪除RSS連結（交互式）')
    
    args = parser.parse_args()
    
    manager = NhentaiRssManager(opml_file=args.file)
    
    if args.list:
        manager.list_rss()
    elif args.add:
        manager.add_rss(args.add)
    elif args.delete:
        manager.delete_rss(interactive=True)
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 