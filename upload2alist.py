#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AList v3 – 以 /api/fs/form 將檔案上傳至指定路徑

先 pip install requests
"""

import os
import requests
import urllib.parse

# === 從環境變數獲取設定 ===
ALIST_BASE = os.environ.get("ALIST_BASE", "http://your-alist-server")  # 末尾不要加 '/'
USERNAME   = os.environ.get("ALIST_USERNAME", "your_username")
PASSWORD   = os.environ.get("ALIST_PASSWORD", "your_password")
REMOTE_DIR = os.environ.get("ALIST_REMOTE_DIR", "/book/nh")  # AList 端的目錄（根目錄請用 /）

def upload_file(LOCAL_FILE):
    """上傳檔案到 AList 伺服器"""
    try:
        # ------------------------------------------------------------
        # 1) 登入換取 JWT token
        auth_resp = requests.post(
            f"{ALIST_BASE}/api/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=30,
        )
        auth_resp.raise_for_status()
        token = auth_resp.json()["data"]["token"]

        # 2) 組出上傳所需的 File-Path（需 URL‑encoding）
        remote_name = os.path.basename(LOCAL_FILE)
        file_path_header = urllib.parse.quote(f"{REMOTE_DIR.rstrip('/')}/{remote_name}")

        # 3) 讀檔並上傳
        with open(LOCAL_FILE, "rb") as fp:
            file_size = os.fstat(fp.fileno()).st_size
            headers = {
                "Authorization": token,
                "File-Path": file_path_header,
                # 下一行非嚴格必需，但建議帶上以減少伺服器判斷
                "Content-Length": str(file_size),
            }
            files = {"file": fp}  # requests 會自動生成 multipart boundary
            upload_resp = requests.put(
                f"{ALIST_BASE}/api/fs/form",
                headers=headers,
                files=files,
                timeout=300,
            )
            upload_resp.raise_for_status()
            print("AList 回應：", upload_resp.json())
            return True
    except Exception as e:
        print(f"上傳失敗：{e}")
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        LOCAL_FILE = sys.argv[1]
        upload_file(LOCAL_FILE)
    else:
        print("用法：python upload2alist.py <要上傳的檔案路徑>")
