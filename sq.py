#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3
import os

# 設定數據庫路徑
db_path = "output/nh/downloaded.db"

# 確保數據庫文件存在
if not os.path.exists(db_path):
    print(f"錯誤：找不到數據庫文件 {db_path}")
    exit(1)

try:
    # 連接到數據庫
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 查詢倒數兩個記錄的ID
    cursor.execute("SELECT id FROM downloaded ORDER BY id DESC LIMIT 2")
    results = cursor.fetchall()
    
    if len(results) < 2:
        print("數據庫中記錄不足兩條")
    else:
        # 更新指定ID的上傳狀態
        for id_tuple in results:
            id_value = id_tuple[0]
            cursor.execute("UPDATE downloaded SET uploaded = 1 WHERE id = ?", (id_value,))
            print(f"已將ID為 {id_value} 的記錄上傳狀態設為0")
    
    # 提交更改並關閉連接
    conn.commit()
    print("成功更新數據庫")
    
    # 顯示更新後的記錄
    cursor.execute("SELECT id, title, uploaded FROM downloaded ORDER BY id DESC LIMIT 5")
    print("\n最新的5條記錄：")
    print("ID\t標題\t上傳狀態")
    for row in cursor.fetchall():
        print(f"{row[0]}\t{row[1][:30]}...\t{row[2]}")
    
    conn.close()

except Exception as e:
    print(f"操作數據庫時出錯：{e}")