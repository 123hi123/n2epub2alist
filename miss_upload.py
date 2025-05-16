#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3
import os
import sys
import logging
import time
from main import NHentaiDownloader

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mark_downloaded.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def recover_failed_downloads():
    """恢復失敗的下載"""
    try:
        downloader = NHentaiDownloader()
        return downloader.recover_failed_downloads()
    except Exception as e:
        logger.error(f"恢復失敗的下載時發生錯誤: {e}")
        return 0

def upload_missing_files(base_dir='output/nh'):
    """上傳未成功上傳的檔案"""
    try:
        # 初始化下載器（僅用於上傳功能）
        downloader = NHentaiDownloader(base_dir=base_dir, upload_to_alist=True)
        
        # 連接資料庫
        db_path = os.path.join(base_dir, 'downloaded.db')
        if not os.path.exists(db_path):
            logger.error(f"資料庫不存在: {db_path}")
            return 0
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查詢所有已下載但未上傳的檔案
        cursor.execute("SELECT id, title, url, file_path FROM downloaded WHERE uploaded = 0")
        files = cursor.fetchall()
        
        logger.info(f"找到 {len(files)} 個未上傳的檔案")
        
        uploaded_count = 0
        for file_id, title, url, file_path in files:
            if os.path.exists(file_path):
                logger.info(f"正在上傳: {title}")
                # 使用與原始程式相同的時間戳目錄格式
                time_dir = os.path.basename(os.path.dirname(file_path))
                remote_dir = f"/book/nh/{time_dir}"
                
                # 嘗試上傳
                if downloader.upload_to_alist_server(file_path, remote_dir):
                    # 更新上傳狀態
                    cursor.execute("UPDATE downloaded SET uploaded = 1 WHERE id = ?", (file_id,))
                    conn.commit()
                    logger.info(f"上傳成功: {title}")
                    uploaded_count += 1
                else:
                    logger.error(f"上傳失敗: {title}")
            else:
                logger.warning(f"檔案不存在: {file_path}")
        
        conn.close()
        logger.info(f"完成，共上傳 {uploaded_count} 個檔案")
        return uploaded_count
    
    except Exception as e:
        logger.error(f"上傳未上傳檔案時發生錯誤: {e}")
        return 0

def clean_temp_dirs(base_dir='output/nh', days=3):
    """清理超過指定天數的臨時目錄"""
    try:
        temp_dir = os.path.join(base_dir, 'temp')
        if not os.path.exists(temp_dir):
            logger.warning(f"臨時目錄不存在: {temp_dir}")
            return 0
        
        # 連接臨時檔案追蹤資料庫
        db_path = os.path.join(base_dir, 'temp_tracking.db')
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 查詢所有已完成的臨時目錄
            cursor.execute("SELECT temp_dir FROM temp_files WHERE status = 'completed'")
            completed_dirs = [row[0] for row in cursor.fetchall()]
            
            deleted_count = 0
            for temp_subdir in completed_dirs:
                full_path = temp_subdir
                if os.path.exists(full_path):
                    try:
                        import shutil
                        shutil.rmtree(full_path)
                        logger.info(f"已清理臨時目錄: {full_path}")
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"清理臨時目錄失敗: {full_path}, 錯誤: {e}")
            
            logger.info(f"共清理了 {deleted_count} 個已完成的臨時目錄")
            conn.close()
            
            return deleted_count
        else:
            logger.warning(f"臨時檔案追蹤資料庫不存在: {db_path}")
            return 0
    
    except Exception as e:
        logger.error(f"清理臨時目錄時發生錯誤: {e}")
        return 0

if __name__ == "__main__":
    logger.info("開始執行維護任務...")
    
    # 恢復失敗的下載
    recovered = recover_failed_downloads()
    logger.info(f"已恢復 {recovered} 個失敗的下載任務")
    
    # 上傳未上傳的檔案
    uploaded = upload_missing_files()
    logger.info(f"已上傳 {uploaded} 個未上傳的檔案")
    
    # 清理臨時目錄
    cleaned = clean_temp_dirs()
    logger.info(f"已清理 {cleaned} 個臨時目錄")
    
    logger.info("維護任務完成！")