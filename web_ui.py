#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired
import os
import sqlite3
import xml.etree.ElementTree as ET
import requests
import time
import json
import feedparser
import threading
import subprocess
from urllib.parse import urlparse, quote_plus
from functools import wraps
import re

app = Flask(__name__, static_folder='web/static', template_folder='web/templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'link2epub-secret-key')

# 初始化 Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# 設定管理員帳號密碼
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# 定義配置
OPML_FILE_PATH = 'nhentai_rss.opml'
OUTPUT_DIR = 'output/nh'
DOWNLOAD_DB_PATH = os.path.join(OUTPUT_DIR, 'downloaded.db')
TEMP_TRACKING_DB_PATH = os.path.join(OUTPUT_DIR, 'temp_tracking.db')

# 常見的中文標籤及其對應
CHINESE_TAGS = {
    "big breasts": "巨乳",
    "milf": "熟女",
    "lolicon": "蘿莉",
    "uncensored": "無修正",
    "full color": "全彩",
    "chinese": "中文",
    "ahegao": "阿嘿顏",
    "anal": "肛交",
    "bondage": "捆綁",
    "mind control": "精神控制",
    "mind break": "精神崩潰",
    "netorare": "NTR",
    "schoolgirl": "女學生",
    "swimsuit": "泳裝",
    "teacher": "老師",
    "stockings": "絲襪",
    "pantyhose": "連褲襪",
    "nurse": "護士",
    "group": "群交",
    "oral": "口交",
    "threesome": "3P",
    "yuri": "百合",
    "yaoi": "男同",
    "futanari": "扶她",
    "twintails": "雙馬尾",
    "glasses": "眼鏡",
    "maid": "女僕",
    "oppai": "巨乳",
    "sister": "姐妹",
    "incest": "亂倫",
    "mother": "母親",
    "paizuri": "乳交",
    "sole female": "單女主",
    "sole male": "單男主",
    "femdom": "女性支配",
    "monster": "怪物",
    "tentacles": "觸手",
    "defloration": "破處",
    "x-ray": "透視",
    "blowjob": "口交",
    "dilf": "熟男",
}

# 使用者模型
class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

# 建立管理員
admin = User(1, ADMIN_USERNAME, ADMIN_PASSWORD)

# 登入表單
class LoginForm(FlaskForm):
    username = StringField('用戶名', validators=[DataRequired()])
    password = PasswordField('密碼', validators=[DataRequired()])
    remember = BooleanField('記住我')
    submit = SubmitField('登入')

# RSS訂閱表單
class RssForm(FlaskForm):
    title = StringField('標題', validators=[DataRequired()])
    url = StringField('RSS URL', validators=[DataRequired()])
    submit = SubmitField('添加')

# 用戶載入回調
@login_manager.user_loader
def load_user(user_id):
    if int(user_id) == 1:
        return admin
    return None

# 管理員權限檢查
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.username != ADMIN_USERNAME:
            flash('需要管理員權限', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# 資料庫操作函數
def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# 解析OPML檔案
def parse_opml():
    try:
        if not os.path.exists(OPML_FILE_PATH):
            root = ET.Element("opml")
            root.set("version", "2.0")
            body = ET.SubElement(root, "body")
            tree = ET.ElementTree(root)
            tree.write(OPML_FILE_PATH, encoding='utf-8', xml_declaration=True)
            return []

        tree = ET.parse(OPML_FILE_PATH)
        root = tree.getroot()
        
        rss_sources = []
        for outline in root.findall(".//outline"):
            if outline.get("type") == "rss" and outline.get("xmlUrl"):
                rss_sources.append({
                    "title": outline.get("title", ""),
                    "url": outline.get("xmlUrl", ""),
                    "html_url": outline.get("htmlUrl", "")
                })
        
        return rss_sources
    except Exception as e:
        print(f"解析OPML檔案失敗: {e}")
        return []

# 添加RSS源到OPML
def add_rss_to_opml(title, rss_url, html_url=""):
    try:
        # 檢查是否為有效的RSS
        feed = feedparser.parse(rss_url)
        if not feed.entries and not feed.feed:
            return False, "無效的RSS源"
        
        # 檢查URL是否包含nhentai相關關鍵字
        if "nhentai" not in rss_url.lower():
            return False, "只支持nhentai相關的RSS源"
        
        # 解析並更新OPML
        if os.path.exists(OPML_FILE_PATH):
            tree = ET.parse(OPML_FILE_PATH)
            root = tree.getroot()
        else:
            root = ET.Element("opml")
            root.set("version", "2.0")
            ET.SubElement(root, "head")
            ET.SubElement(root, "body")
            
        body = root.find(".//body")
        if body is None:
            body = ET.SubElement(root, "body")
        
        # 檢查是否已存在相同URL的訂閱
        for outline in body.findall("./outline"):
            if outline.get("xmlUrl") == rss_url:
                return False, "此RSS源已存在"
        
        # 添加新的RSS源
        outline = ET.SubElement(body, "outline")
        outline.set("text", title)
        outline.set("title", title)
        outline.set("xmlUrl", rss_url)
        outline.set("htmlUrl", html_url)
        outline.set("type", "rss")
        
        # 寫入檔案
        tree = ET.ElementTree(root)
        tree.write(OPML_FILE_PATH, encoding='utf-8', xml_declaration=True)
        return True, "RSS源添加成功"
    except Exception as e:
        return False, f"添加RSS源失敗: {e}"

# 刪除RSS源
def delete_rss_from_opml(rss_url):
    try:
        tree = ET.parse(OPML_FILE_PATH)
        root = tree.getroot()
        
        for outline in root.findall(".//outline"):
            if outline.get("xmlUrl") == rss_url:
                parent = outline.getparent() or root.find(".//body")
                if parent is not None:
                    parent.remove(outline)
                
        tree.write(OPML_FILE_PATH, encoding='utf-8', xml_declaration=True)
        return True, "RSS源刪除成功"
    except Exception as e:
        return False, f"刪除RSS源失敗: {e}"

# 檢查RSS源是否有效
def check_rss_valid(rss_url):
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries or feed.feed:
            # 從RSS獲取標籤信息
            tags = []
            if feed.entries:
                for entry in feed.entries[:1]:
                    title = entry.get('title', '')
                    for tag in CHINESE_TAGS:
                        if tag.lower() in title.lower():
                            tags.append(CHINESE_TAGS[tag])
            return True, {"valid": True, "message": "RSS源有效", "tags": tags}
        return False, {"valid": False, "message": "無效的RSS源"}
    except Exception as e:
        return False, {"valid": False, "message": f"檢查RSS失敗: {e}"}

# 獲取下載歷史
def get_download_history():
    try:
        conn = get_db_connection(DOWNLOAD_DB_PATH)
        downloads = conn.execute('SELECT * FROM downloaded ORDER BY download_date DESC').fetchall()
        conn.close()
        return downloads
    except Exception as e:
        print(f"獲取下載歷史失敗: {e}")
        return []

# 獲取臨時文件狀態
def get_temp_files_status():
    try:
        conn = get_db_connection(TEMP_TRACKING_DB_PATH)
        temp_files = conn.execute('SELECT * FROM temp_files ORDER BY created_time DESC').fetchall()
        conn.close()
        return temp_files
    except Exception as e:
        print(f"獲取臨時文件狀態失敗: {e}")
        return []

# 啟動下載任務
def start_download_task(use_external_links=False, upload_to_alist=False):
    # 使用子進程執行下載任務
    cmd = ["python", "main.py", "-o", OPML_FILE_PATH]
    if use_external_links:
        cmd.append("-e")
    if upload_to_alist:
        cmd.append("-u")
    
    subprocess.Popen(cmd)
    return True

# 路由
@app.route('/')
@login_required
def index():
    rss_sources = parse_opml()
    download_history = get_download_history()
    temp_files = get_temp_files_status()
    
    # 計算統計信息
    stats = {
        "total_downloads": len(download_history),
        "uploaded_count": sum(1 for item in download_history if item['uploaded'] == 1),
        "pending_uploads": sum(1 for item in download_history if item['uploaded'] == 0),
        "active_temp_dirs": sum(1 for item in temp_files if item['status'] != 'completed')
    }
    
    return render_template('index.html', 
                          rss_sources=rss_sources,
                          download_history=download_history[:20],  # 只顯示最近20條
                          temp_files=temp_files[:20],  # 只顯示最近20條
                          stats=stats)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if form.username.data == ADMIN_USERNAME and form.password.data == ADMIN_PASSWORD:
            login_user(admin, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('用戶名或密碼錯誤', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已登出', 'success')
    return redirect(url_for('login'))

@app.route('/rss', methods=['GET', 'POST'])
@login_required
def rss_management():
    form = RssForm()
    if form.validate_on_submit():
        html_url = ""
        if "nhentai" in form.url.data:
            # 從RSS URL推導HTML URL
            query_match = re.search(r'/search/([^/]+)/detail', form.url.data)
            if query_match:
                query = query_match.group(1)
                html_url = f"https://nhentai.net/search/?q={quote_plus(query)}"
        
        success, message = add_rss_to_opml(form.title.data, form.url.data, html_url)
        if success:
            flash(message, 'success')
        else:
            flash(message, 'danger')
        return redirect(url_for('rss_management'))
    
    rss_sources = parse_opml()
    return render_template('rss_management.html', form=form, rss_sources=rss_sources, chinese_tags=CHINESE_TAGS)

@app.route('/rss/delete/<path:rss_url>', methods=['POST'])
@login_required
def delete_rss(rss_url):
    success, message = delete_rss_from_opml(rss_url)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    return redirect(url_for('rss_management'))

@app.route('/api/check-rss', methods=['POST'])
@login_required
def check_rss():
    rss_url = request.json.get('url', '')
    success, result = check_rss_valid(rss_url)
    return jsonify(result)

@app.route('/download')
@login_required
def download_management():
    download_history = get_download_history()
    temp_files = get_temp_files_status()
    return render_template('download_management.html', 
                          download_history=download_history,
                          temp_files=temp_files)

@app.route('/start-download', methods=['POST'])
@login_required
def start_download():
    use_external_links = request.form.get('external_links') == 'true'
    upload_to_alist = request.form.get('upload') == 'true'
    
    if start_download_task(use_external_links, upload_to_alist):
        flash('下載任務已啟動', 'success')
    else:
        flash('啟動下載任務失敗', 'danger')
    
    return redirect(url_for('download_management'))

@app.route('/system')
@login_required
@admin_required
def system_management():
    # 獲取系統信息
    disk_usage = os.popen("df -h /app | tail -n 1").read().strip()
    temp_size = os.popen("du -sh /app/output/nh/temp").read().strip()
    output_size = os.popen("du -sh /app/output/nh").read().strip()
    
    return render_template('system_management.html',
                          disk_usage=disk_usage,
                          temp_size=temp_size,
                          output_size=output_size)

@app.route('/system/clean-temp', methods=['POST'])
@login_required
@admin_required
def clean_temp():
    days = request.form.get('days', 1, type=int)
    cmd = f"find /app/output/nh/temp -type d -mtime +{days} -exec rm -rf {{}} \\; 2>/dev/null || true"
    os.system(cmd)
    flash(f'已清理{days}天前的臨時文件', 'success')
    return redirect(url_for('system_management'))

@app.route('/download/epub/<int:download_id>')
@login_required
def download_epub(download_id):
    try:
        conn = get_db_connection(DOWNLOAD_DB_PATH)
        download = conn.execute('SELECT file_path FROM downloaded WHERE id = ?', (download_id,)).fetchone()
        conn.close()
        
        if download and os.path.exists(download['file_path']):
            return send_file(download['file_path'], as_attachment=True)
        else:
            flash('文件不存在', 'danger')
            return redirect(url_for('download_management'))
    except Exception as e:
        flash(f'下載文件失敗: {e}', 'danger')
        return redirect(url_for('download_management'))

# 初始化資料庫
def init_db():
    # 確保下載歷史資料庫存在
    conn = sqlite3.connect(DOWNLOAD_DB_PATH)
    conn.execute('''
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
    conn.close()
    
    # 確保臨時文件追蹤資料庫存在
    conn = sqlite3.connect(TEMP_TRACKING_DB_PATH)
    conn.execute('''
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
    conn.close()

# 確保目錄存在
def ensure_directories():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, 'temp'), exist_ok=True)
    os.makedirs('temp', exist_ok=True)
    os.makedirs('web/templates', exist_ok=True)
    os.makedirs('web/static/css', exist_ok=True)
    os.makedirs('web/static/js', exist_ok=True)

if __name__ == '__main__':
    ensure_directories()
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False) 