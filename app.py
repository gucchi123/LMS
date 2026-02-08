from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import sqlite3
import os
import json
import re
import unicodedata
from datetime import datetime
import threading

# Whisper（オプション - ローカル環境のみ）
WHISPER_AVAILABLE = False
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    pass  # Whisperがインストールされていない環境（PythonAnywhereなど）

# 環境変数読み込み（dotenvがある場合のみ）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # PythonAnywhereではWSGIファイルで環境変数を設定

# Rakuten AI 3.0 API用
import httpx

# 日本語→ローマ字変換
import pykakasi

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
app.config['UPLOAD_FOLDER'] = 'videos'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['DATABASE'] = os.environ.get('LMS_DATABASE', 'lms.db')
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}

# ========== Rakuten AI 3.0 API設定 ==========
# APIキーは環境変数または.envファイルから読み込み（ハードコード禁止）
RAKUTEN_AI_API_KEY = os.environ.get('RAKUTEN_AI_API_KEY', '')
RAKUTEN_AI_BASE_URL = os.environ.get('RAKUTEN_AI_BASE_URL', 'https://api.ai.public.rakuten-it.com/rakutenllms/v1/')
RAKUTEN_AI_MODEL = os.environ.get('RAKUTEN_AI_MODEL', 'rakutenai-3.0')

# ========== GA4 設定 ==========
GA_MEASUREMENT_ID = os.environ.get('GA_MEASUREMENT_ID', '')

# GA4 Measurement IDをすべてのテンプレートに渡す
@app.context_processor
def inject_ga():
    return {'ga_measurement_id': GA_MEASUREMENT_ID}

# データベース接続
def get_db():
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    return db

# データベースマイグレーション（transcription_status, summaryカラム追加）
def migrate_transcription_columns():
    """既存のDBにtranscription_statusとsummaryカラムを追加"""
    db = get_db()
    cursor = db.cursor()
    
    # カラムの存在確認
    cursor.execute("PRAGMA table_info(videos)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'transcription_status' not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN transcription_status TEXT DEFAULT 'none'")
        print("[Migration] Added transcription_status column to videos table")
    
    if 'summary' not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN summary TEXT")
        print("[Migration] Added summary column to videos table")
    
    db.commit()
    db.close()

# データベースマイグレーション（テナント・部署・ロール対応）
def migrate_tenant_role_columns():
    """既存のDBにtenant_id, department_id, roleカラムを追加"""
    db = get_db()
    cursor = db.cursor()
    
    # テナントテーブル作成
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        industry_id INTEGER,
        logo TEXT,
        settings TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (industry_id) REFERENCES industries (id)
    )
    ''')
    
    # 部署テーブル作成
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        parent_department_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
        FOREIGN KEY (parent_department_id) REFERENCES departments (id)
    )
    ''')
    
    # アクセスログテーブル作成
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        tenant_id INTEGER,
        path TEXT NOT NULL,
        method TEXT DEFAULT 'GET',
        status_code INTEGER,
        user_agent TEXT,
        ip_address TEXT,
        referrer TEXT,
        duration_ms INTEGER,
        extra TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (tenant_id) REFERENCES tenants (id)
    )
    ''')
    
    # usersテーブルのカラム追加
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'tenant_id' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tenant_id INTEGER REFERENCES tenants(id)")
        print("[Migration] Added tenant_id column to users table")
    
    if 'department_id' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN department_id INTEGER REFERENCES departments(id)")
        print("[Migration] Added department_id column to users table")
    
    if 'role' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
        # 既存のis_admin=1のユーザーをsuper_adminに移行
        cursor.execute("UPDATE users SET role = 'super_admin' WHERE is_admin = 1")
        print("[Migration] Added role column to users table, migrated admins to super_admin")
    
    db.commit()
    db.close()

# スラッグ生成関数（日本語→ローマ字変換対応）
_kakasi = None

def get_kakasi():
    """pykakasi インスタンスを取得（シングルトン）"""
    global _kakasi
    if _kakasi is None:
        _kakasi = pykakasi.kakasi()
    return _kakasi

def generate_slug(title, existing_slugs=None):
    """タイトルからURLスラッグを生成（英語ローマ字）"""
    # 正規化（NFKC）
    text = unicodedata.normalize('NFKC', title)
    
    # 日本語をローマ字に変換
    kakasi = get_kakasi()
    result = kakasi.convert(text)
    # ローマ字部分を結合
    slug = '-'.join([item['hepburn'] for item in result if item['hepburn'].strip()])
    
    # 小文字に変換
    slug = slug.lower()
    # 英数字とハイフン以外を削除
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    # 連続ハイフンを1つに
    slug = re.sub(r'-+', '-', slug)
    # 前後のハイフンを削除
    slug = slug.strip('-')
    
    # 空の場合はフォールバック
    if not slug:
        slug = 'item'
    
    # 重複チェック
    if existing_slugs:
        base_slug = slug
        counter = 2
        while slug in existing_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1
    
    return slug

# データベースからスラッグを生成（既存データ用）
def ensure_slug_for_category(db, category_id):
    """カテゴリーにスラッグがなければ生成"""
    cat = db.execute('SELECT id, name, slug FROM categories WHERE id = ?', (category_id,)).fetchone()
    if cat and not cat['slug']:
        existing = db.execute('SELECT slug FROM categories WHERE slug IS NOT NULL').fetchall()
        existing_slugs = {r['slug'] for r in existing}
        slug = generate_slug(cat['name'], existing_slugs)
        db.execute('UPDATE categories SET slug = ? WHERE id = ?', (slug, category_id))
        db.commit()
        return slug
    return cat['slug'] if cat else None

def ensure_slug_for_video(db, video_id):
    """動画にスラッグがなければ生成"""
    video = db.execute('SELECT id, title, slug FROM videos WHERE id = ?', (video_id,)).fetchone()
    if video and not video['slug']:
        existing = db.execute('SELECT slug FROM videos WHERE slug IS NOT NULL').fetchall()
        existing_slugs = {r['slug'] for r in existing}
        slug = generate_slug(video['title'], existing_slugs)
        db.execute('UPDATE videos SET slug = ? WHERE id = ?', (slug, video_id))
        db.commit()
        return slug
    return video['slug'] if video else None

# カテゴリーアクセス権チェック（業種ベース）
def can_access_category(db, category_id, industry_id, is_admin):
    """ユーザーがカテゴリーにアクセスできるかチェック"""
    # 管理者は全てにアクセス可能
    if is_admin:
        return True
    
    # アクセス制御レコードがあるか確認
    access_records = db.execute(
        'SELECT industry_id FROM category_industry_access WHERE category_id = ?',
        (category_id,)
    ).fetchall()
    
    # レコードがない場合は全業種公開
    if not access_records:
        return True
    
    # 業種IDがない場合（管理者以外で業種未設定）はアクセス不可
    if industry_id is None:
        return False
    
    # ユーザーの業種がアクセス許可リストに含まれているか
    allowed_industries = [r['industry_id'] for r in access_records]
    return industry_id in allowed_industries

# アクセス可能なカテゴリーIDリストを取得（業種ベース）
def get_accessible_category_ids(db, industry_id, is_admin):
    """ユーザーがアクセス可能なカテゴリーIDリストを取得"""
    if is_admin:
        # 管理者は全カテゴリーにアクセス可能
        categories = db.execute('SELECT id FROM categories').fetchall()
        return [c['id'] for c in categories]
    
    # 全カテゴリーを取得
    all_categories = db.execute('SELECT id FROM categories').fetchall()
    
    accessible = []
    for cat in all_categories:
        if can_access_category(db, cat['id'], industry_id, is_admin):
            accessible.append(cat['id'])
    
    return accessible

# ファイル拡張子チェック
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ログイン必須デコレータ
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# 管理者権限デコレータ（後方互換）
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        role = session.get('role', 'user')
        if role not in ('super_admin', 'company_admin'):
            # 旧is_adminフラグとの後方互換
            db = get_db()
            user = db.execute('SELECT is_admin, role FROM users WHERE id = ?', (session['user_id'],)).fetchone()
            if not user or (not user['is_admin'] and user['role'] not in ('super_admin', 'company_admin')):
                return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ロールベース権限デコレータ
def role_required(*roles):
    """指定されたロールのいずれかを持つユーザーのみアクセスを許可"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            user_role = session.get('role', 'user')
            if user_role not in roles:
                return jsonify({'error': f'この操作には{"/".join(roles)}権限が必要です'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# テナント境界フィルタリングヘルパー
def get_tenant_filter(session_data):
    """セッション情報からテナント境界のフィルタリング条件を返す"""
    role = session_data.get('role', 'user')
    tenant_id = session_data.get('tenant_id')
    
    if role == 'super_admin':
        return None, None  # 全テナント横断
    else:
        return tenant_id, tenant_id  # 自テナントのみ

# ルート - コースカタログへリダイレクト
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('course_catalog'))
    return redirect(url_for('login'))

# ログインページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            session['industry_id'] = user['industry_id']
            session['company_name'] = user['company_name']
            
            # ロール・テナント・部署情報をセッションに保存
            session['role'] = user['role'] if 'role' in user.keys() else ('super_admin' if user['is_admin'] else 'user')
            session['tenant_id'] = user['tenant_id'] if 'tenant_id' in user.keys() else None
            session['department_id'] = user['department_id'] if 'department_id' in user.keys() else None
            
            # 業種名を取得
            if user['industry_id']:
                industry = db.execute('SELECT name FROM industries WHERE id = ?', (user['industry_id'],)).fetchone()
                session['industry_name'] = industry['name'] if industry else None
            else:
                session['industry_name'] = None
            
            return jsonify({'success': True, 'is_admin': user['is_admin'], 'role': session['role']})
        
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    
    return render_template('login.html')

# ログアウト
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# コースカタログ（カテゴリー一覧）
@app.route('/courses')
@login_required
def course_catalog():
    db = get_db()
    industry_id = session.get('industry_id')
    is_admin = session.get('is_admin')
    
    # アクセス可能なカテゴリーIDを取得
    accessible_ids = get_accessible_category_ids(db, industry_id, is_admin)
    
    # トップレベルカテゴリーを取得
    categories = db.execute('''
        SELECT c.*, 
               (SELECT COUNT(*) FROM videos WHERE category_id = c.id) as video_count,
               (SELECT COUNT(*) FROM categories WHERE parent_id = c.id) as subcategory_count
        FROM categories c
        WHERE c.parent_id IS NULL
        ORDER BY c.display_order, c.created_at
    ''').fetchall()
    
    # アクセス可能なカテゴリーのみフィルタリング
    category_data = []
    for cat in categories:
        if cat['id'] not in accessible_ids:
            continue
        cat_dict = dict(cat)
        # サブカテゴリー内の動画数を集計（アクセス可能なもののみ）
        sub_video_count = db.execute('''
            SELECT COUNT(*) as count FROM videos v
            JOIN categories c ON v.category_id = c.id
            WHERE c.parent_id = ? AND c.id IN ({})
        '''.format(','.join('?' * len(accessible_ids))), 
        (cat['id'], *accessible_ids)).fetchone()
        cat_dict['total_video_count'] = cat['video_count'] + (sub_video_count['count'] if sub_video_count else 0)
        category_data.append(cat_dict)
    
    return render_template('course_catalog.html', categories=category_data)

# カテゴリー詳細ページ
@app.route('/courses/<slug_or_id>')
@login_required
def category_detail(slug_or_id):
    db = get_db()
    industry_id = session.get('industry_id')
    is_admin = session.get('is_admin')
    
    # IDまたはスラッグでカテゴリーを検索（後方互換性）
    if slug_or_id.isdigit():
        category = db.execute('SELECT * FROM categories WHERE id = ?', (int(slug_or_id),)).fetchone()
    else:
        category = db.execute('SELECT * FROM categories WHERE slug = ?', (slug_or_id,)).fetchone()
    
    if not category:
        return "Category not found", 404
    
    category_id = category['id']
    
    # スラッグがなければ生成
    if not category['slug']:
        ensure_slug_for_category(db, category_id)
    
    # アクセス権チェック
    if not can_access_category(db, category_id, industry_id, is_admin):
        return "このカテゴリーへのアクセス権限がありません", 403
    
    # 親カテゴリー情報を取得（パンくず用）
    parent = None
    if category['parent_id']:
        parent = db.execute('SELECT * FROM categories WHERE id = ?', (category['parent_id'],)).fetchone()
    
    # アクセス可能なカテゴリーIDを取得
    accessible_ids = get_accessible_category_ids(db, industry_id, is_admin)
    
    # サブカテゴリーを取得（アクセス可能なもののみ）
    all_subcategories = db.execute('''
        SELECT c.*, 
               (SELECT COUNT(*) FROM videos WHERE category_id = c.id) as video_count
        FROM categories c
        WHERE c.parent_id = ?
        ORDER BY c.display_order, c.created_at
    ''', (category_id,)).fetchall()
    
    subcategories = [s for s in all_subcategories if s['id'] in accessible_ids]
    
    # このカテゴリーの動画を取得
    videos = db.execute('''
        SELECT * FROM videos WHERE category_id = ?
        ORDER BY created_at DESC
    ''', (category_id,)).fetchall()
    
    # 各動画の視聴進捗を取得
    video_progress = {}
    for video in videos:
        progress = db.execute(
            'SELECT progress_percent FROM progress WHERE user_id = ? AND video_id = ?',
            (session['user_id'], video['id'])
        ).fetchone()
        video_progress[video['id']] = progress['progress_percent'] if progress else 0
    
    return render_template('category_detail.html', 
                           category=category, 
                           parent=parent,
                           subcategories=subcategories, 
                           videos=videos,
                           video_progress=video_progress)

# ダッシュボード（全動画一覧）
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    industry_id = session.get('industry_id')
    is_admin = session.get('is_admin', False)
    
    # アクセス可能なカテゴリーIDを取得（業種フィルタリング）
    accessible_ids = get_accessible_category_ids(db, industry_id, is_admin)
    
    if accessible_ids:
        placeholders = ','.join('?' * len(accessible_ids))
        videos = db.execute(f'''
            SELECT v.*, c.name as category_name, c.color as category_color
            FROM videos v
            LEFT JOIN categories c ON v.category_id = c.id
            WHERE v.category_id IN ({placeholders})
               OR v.category_id IS NULL
            ORDER BY v.created_at DESC
        ''', accessible_ids).fetchall()
    else:
        videos = db.execute('''
            SELECT v.*, c.name as category_name, c.color as category_color
            FROM videos v
            LEFT JOIN categories c ON v.category_id = c.id
            WHERE v.category_id IS NULL
            ORDER BY v.created_at DESC
        ''').fetchall()
    
    # 各動画の視聴進捗を取得
    video_progress = {}
    for video in videos:
        progress = db.execute(
            'SELECT progress_percent FROM progress WHERE user_id = ? AND video_id = ?',
            (session['user_id'], video['id'])
        ).fetchone()
        video_progress[video['id']] = progress['progress_percent'] if progress else 0
    
    return render_template('dashboard.html', videos=videos, video_progress=video_progress)

# 動画視聴ページ
@app.route('/watch/<slug_or_id>')
@login_required
def watch_video(slug_or_id):
    db = get_db()
    
    # IDまたはスラッグで動画を検索（後方互換性）
    if slug_or_id.isdigit():
        video = db.execute('SELECT * FROM videos WHERE id = ?', (int(slug_or_id),)).fetchone()
    else:
        video = db.execute('SELECT * FROM videos WHERE slug = ?', (slug_or_id,)).fetchone()
    
    if not video:
        return "Video not found", 404
    
    video_id = video['id']
    
    # 業種ベースのアクセス制御チェック
    if video['category_id']:
        industry_id = session.get('industry_id')
        is_admin = session.get('is_admin', False)
        if not can_access_category(db, video['category_id'], industry_id, is_admin):
            return "この動画にアクセスする権限がありません", 403
    
    # スラッグがなければ生成
    if not video['slug']:
        ensure_slug_for_video(db, video_id)
    
    # 視聴進捗を取得
    progress = db.execute(
        'SELECT progress_percent, last_position FROM progress WHERE user_id = ? AND video_id = ?',
        (session['user_id'], video_id)
    ).fetchone()
    
    last_position = progress['last_position'] if progress else 0
    
    return render_template('watch.html', video=video, last_position=last_position)

# 動画ファイル配信
@app.route('/videos/<filename>')
@login_required
def serve_video(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# 進捗保存API
@app.route('/api/progress', methods=['POST'])
@login_required
def save_progress():
    data = request.json
    video_id = data.get('video_id')
    progress_percent = data.get('progress_percent')
    last_position = data.get('last_position')
    
    db = get_db()
    
    # 既存の進捗をチェック
    existing = db.execute(
        'SELECT id FROM progress WHERE user_id = ? AND video_id = ?',
        (session['user_id'], video_id)
    ).fetchone()
    
    if existing:
        db.execute(
            'UPDATE progress SET progress_percent = ?, last_position = ?, updated_at = ? WHERE user_id = ? AND video_id = ?',
            (progress_percent, last_position, datetime.now(), session['user_id'], video_id)
        )
    else:
        db.execute(
            'INSERT INTO progress (user_id, video_id, progress_percent, last_position) VALUES (?, ?, ?, ?)',
            (session['user_id'], video_id, progress_percent, last_position)
        )
    
    db.commit()
    return jsonify({'success': True})

# 管理者ダッシュボード
@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    
    videos = db.execute('''
        SELECT v.*, c.name as category_name 
        FROM videos v 
        LEFT JOIN categories c ON v.category_id = c.id 
        ORDER BY v.created_at DESC
    ''').fetchall()
    
    # テナント境界フィルタリング（company_adminは自テナントのユーザーのみ表示）
    if role == 'super_admin':
        users = db.execute('''
            SELECT u.id, u.username, u.email, u.company_name, u.role, u.tenant_id, 
                   u.department_id, u.created_at, i.name as industry_name,
                   t.name as tenant_name, d.name as department_name
            FROM users u
            LEFT JOIN industries i ON u.industry_id = i.id
            LEFT JOIN tenants t ON u.tenant_id = t.id
            LEFT JOIN departments d ON u.department_id = d.id
            ORDER BY u.created_at DESC
        ''').fetchall()
    else:
        users = db.execute('''
            SELECT u.id, u.username, u.email, u.company_name, u.role, u.tenant_id, 
                   u.department_id, u.created_at, i.name as industry_name,
                   t.name as tenant_name, d.name as department_name
            FROM users u
            LEFT JOIN industries i ON u.industry_id = i.id
            LEFT JOIN tenants t ON u.tenant_id = t.id
            LEFT JOIN departments d ON u.department_id = d.id
            WHERE u.tenant_id = ?
            ORDER BY u.created_at DESC
        ''', (tenant_id,)).fetchall()
    
    categories = db.execute('SELECT * FROM categories ORDER BY display_order, created_at').fetchall()
    industries = db.execute('SELECT * FROM industries ORDER BY id').fetchall()
    
    # テナント一覧を取得
    tenants = db.execute('''
        SELECT t.*, i.name as industry_name 
        FROM tenants t 
        LEFT JOIN industries i ON t.industry_id = i.id 
        ORDER BY t.name
    ''').fetchall()
    
    # 部署一覧を取得（テナント境界フィルタリング）
    if role == 'super_admin':
        departments = db.execute('''
            SELECT d.*, t.name as tenant_name 
            FROM departments d 
            JOIN tenants t ON d.tenant_id = t.id 
            ORDER BY t.name, d.name
        ''').fetchall()
    elif tenant_id:
        departments = db.execute('''
            SELECT d.*, t.name as tenant_name 
            FROM departments d 
            JOIN tenants t ON d.tenant_id = t.id 
            WHERE d.tenant_id = ?
            ORDER BY d.name
        ''', (tenant_id,)).fetchall()
    else:
        departments = []
    
    # 各カテゴリーのアクセス制御情報を取得
    category_access = {}
    for cat in categories:
        access = db.execute('''
            SELECT i.id, i.name FROM industries i
            JOIN category_industry_access cia ON i.id = cia.industry_id
            WHERE cia.category_id = ?
        ''', (cat['id'],)).fetchall()
        category_access[cat['id']] = [dict(a) for a in access]
    
    # 外部ナレッジを取得（company_adminは自業種のみ）
    knowledge_list = []
    try:
        if role == 'super_admin':
            knowledge_list = db.execute('''
                SELECT ek.id, ek.title, ek.source_file, ek.keywords, ek.created_at,
                       i.name as industry_name, i.id as industry_id
                FROM external_knowledge ek
                LEFT JOIN industries i ON ek.industry_id = i.id
                ORDER BY ek.created_at DESC
            ''').fetchall()
        else:
            # company_adminは自テナントの業種に関連するナレッジのみ表示
            user_industry_id = session.get('industry_id')
            if user_industry_id:
                knowledge_list = db.execute('''
                    SELECT ek.id, ek.title, ek.source_file, ek.keywords, ek.created_at,
                           i.name as industry_name, i.id as industry_id
                    FROM external_knowledge ek
                    LEFT JOIN industries i ON ek.industry_id = i.id
                    WHERE ek.industry_id = ?
                    ORDER BY ek.created_at DESC
                ''', (user_industry_id,)).fetchall()
            else:
                knowledge_list = []
        knowledge_list = [dict(k) for k in knowledge_list]
    except:
        # テーブルが存在しない場合は空リスト
        pass
    
    return render_template('admin.html', videos=videos, users=users, categories=categories, 
                           industries=industries, category_access=category_access,
                           knowledge_list=knowledge_list, tenants=tenants, 
                           departments=departments, current_role=role)

# 動画アップロードAPI
@app.route('/api/admin/upload', methods=['POST'])
@admin_required
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file'}), 400
    
    file = request.files['video']
    title = request.form.get('title')
    description = request.form.get('description', '')
    category_id = request.form.get('category_id')
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # ファイル名の重複を避ける
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # データベースに保存
        db = get_db()
        
        # スラッグを生成
        existing = db.execute('SELECT slug FROM videos WHERE slug IS NOT NULL').fetchall()
        existing_slugs = {r['slug'] for r in existing}
        slug = generate_slug(title, existing_slugs)
        
        db.execute(
            'INSERT INTO videos (title, slug, description, filename, category_id, uploaded_by) VALUES (?, ?, ?, ?, ?, ?)',
            (title, slug, description, filename, category_id if category_id else None, session['user_id'])
        )
        db.commit()
        
        return jsonify({'success': True, 'message': 'Video uploaded successfully'})
    
    return jsonify({'error': 'Invalid file type'}), 400

# 動画削除API
@app.route('/api/admin/delete/<int:video_id>', methods=['DELETE'])
@admin_required
def delete_video(video_id):
    db = get_db()
    video = db.execute('SELECT filename FROM videos WHERE id = ?', (video_id,)).fetchone()
    
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    # ファイルを削除
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], video['filename'])
    if os.path.exists(filepath):
        os.remove(filepath)
    
    # データベースから削除
    db.execute('DELETE FROM videos WHERE id = ?', (video_id,))
    db.execute('DELETE FROM progress WHERE video_id = ?', (video_id,))
    db.commit()
    
    return jsonify({'success': True, 'message': 'Video deleted successfully'})

# 動画更新API
@app.route('/api/admin/update/<int:video_id>', methods=['PUT'])
@admin_required
def update_video(video_id):
    data = request.json
    title = data.get('title')
    description = data.get('description')
    
    db = get_db()
    db.execute(
        'UPDATE videos SET title = ?, description = ? WHERE id = ?',
        (title, description, video_id)
    )
    db.commit()
    
    return jsonify({'success': True, 'message': 'Video updated successfully'})

# ユーザー視聴統計API
@app.route('/api/admin/user-stats/<int:user_id>')
@admin_required
def user_stats(user_id):
    db = get_db()
    stats = db.execute('''
        SELECT v.id, v.title, p.progress_percent, p.last_position, p.updated_at
        FROM videos v
        LEFT JOIN progress p ON v.id = p.video_id AND p.user_id = ?
        ORDER BY v.created_at DESC
    ''', (user_id,)).fetchall()
    
    return jsonify([dict(row) for row in stats])

# ========== カテゴリー管理API ==========

# カテゴリー一覧取得API
@app.route('/api/categories')
@login_required
def get_categories():
    db = get_db()
    categories = db.execute('''
        SELECT c.*, 
               (SELECT COUNT(*) FROM videos WHERE category_id = c.id) as video_count,
               (SELECT COUNT(*) FROM categories WHERE parent_id = c.id) as subcategory_count
        FROM categories c
        ORDER BY c.display_order, c.created_at
    ''').fetchall()
    
    return jsonify([dict(row) for row in categories])

# カテゴリー作成API
@app.route('/api/admin/categories', methods=['POST'])
@admin_required
def create_category():
    data = request.json
    name = data.get('name')
    description = data.get('description', '')
    icon = data.get('icon', 'bi-folder')
    color = data.get('color', '#667eea')
    parent_id = data.get('parent_id')
    display_order = data.get('display_order', 0)
    
    if not name:
        return jsonify({'error': 'カテゴリー名は必須です'}), 400
    
    db = get_db()
    
    # スラッグを生成
    existing = db.execute('SELECT slug FROM categories WHERE slug IS NOT NULL').fetchall()
    existing_slugs = {r['slug'] for r in existing}
    slug = generate_slug(name, existing_slugs)
    
    cursor = db.execute(
        '''INSERT INTO categories (name, slug, description, icon, color, parent_id, display_order)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (name, slug, description, icon, color, parent_id if parent_id else None, display_order)
    )
    db.commit()
    
    return jsonify({
        'success': True, 
        'message': 'カテゴリーを作成しました',
        'id': cursor.lastrowid
    })

# カテゴリー更新API
@app.route('/api/admin/categories/<int:category_id>', methods=['PUT'])
@admin_required
def update_category(category_id):
    data = request.json
    name = data.get('name')
    description = data.get('description', '')
    icon = data.get('icon', 'bi-folder')
    color = data.get('color', '#667eea')
    parent_id = data.get('parent_id')
    display_order = data.get('display_order', 0)
    
    if not name:
        return jsonify({'error': 'カテゴリー名は必須です'}), 400
    
    # 自分自身を親に設定しないようにチェック
    if parent_id and parent_id == category_id:
        return jsonify({'error': '自分自身を親カテゴリーに設定できません'}), 400
    
    db = get_db()
    db.execute(
        '''UPDATE categories 
           SET name = ?, description = ?, icon = ?, color = ?, parent_id = ?, display_order = ?
           WHERE id = ?''',
        (name, description, icon, color, parent_id if parent_id else None, display_order, category_id)
    )
    db.commit()
    
    return jsonify({'success': True, 'message': 'カテゴリーを更新しました'})

# カテゴリー削除API
@app.route('/api/admin/categories/<int:category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    db = get_db()
    
    # サブカテゴリーがあるかチェック
    subcategories = db.execute(
        'SELECT COUNT(*) as count FROM categories WHERE parent_id = ?', 
        (category_id,)
    ).fetchone()
    
    if subcategories['count'] > 0:
        return jsonify({'error': 'サブカテゴリーが存在するため削除できません。先にサブカテゴリーを削除してください。'}), 400
    
    # 動画のカテゴリーをNULLに設定
    db.execute('UPDATE videos SET category_id = NULL WHERE category_id = ?', (category_id,))
    
    # カテゴリーを削除
    db.execute('DELETE FROM categories WHERE id = ?', (category_id,))
    db.commit()
    
    return jsonify({'success': True, 'message': 'カテゴリーを削除しました'})

# 動画のカテゴリー変更API
@app.route('/api/admin/videos/<int:video_id>/category', methods=['PUT'])
@admin_required
def update_video_category(video_id):
    data = request.json
    category_id = data.get('category_id')
    
    db = get_db()
    db.execute(
        'UPDATE videos SET category_id = ? WHERE id = ?',
        (category_id if category_id else None, video_id)
    )
    db.commit()
    
    return jsonify({'success': True, 'message': '動画のカテゴリーを更新しました'})

# ========== カテゴリーアクセス制御API ==========

# カテゴリーのアクセス制御を更新
@app.route('/api/admin/categories/<int:category_id>/access', methods=['PUT'])
@admin_required
def update_category_access(category_id):
    data = request.json
    industry_ids = data.get('industry_ids', [])  # 空リストの場合は全業種公開
    
    db = get_db()
    
    # 既存のアクセス制御を削除
    db.execute('DELETE FROM category_industry_access WHERE category_id = ?', (category_id,))
    
    # 新しいアクセス制御を追加
    for industry_id in industry_ids:
        db.execute(
            'INSERT INTO category_industry_access (category_id, industry_id) VALUES (?, ?)',
            (category_id, industry_id)
        )
    
    db.commit()
    
    return jsonify({'success': True, 'message': 'アクセス権限を更新しました'})

# カテゴリーのアクセス制御を取得
@app.route('/api/admin/categories/<int:category_id>/access')
@admin_required
def get_category_access(category_id):
    db = get_db()
    access = db.execute('''
        SELECT industry_id FROM category_industry_access WHERE category_id = ?
    ''', (category_id,)).fetchall()
    
    return jsonify({
        'category_id': category_id,
        'industry_ids': [a['industry_id'] for a in access],
        'is_public': len(access) == 0  # レコードなし = 全業種公開
    })

# ========== 業種管理API ==========

# 業種一覧取得
@app.route('/api/industries')
@login_required
def get_industries():
    db = get_db()
    industries = db.execute('SELECT * FROM industries ORDER BY id').fetchall()
    return jsonify([dict(row) for row in industries])

# 業種追加
@app.route('/api/admin/industries', methods=['POST'])
@admin_required
def create_industry():
    data = request.json
    name = data.get('name')
    name_en = data.get('name_en', '')
    description = data.get('description', '')
    icon = data.get('icon', 'bi-building')
    color = data.get('color', '#667eea')
    
    if not name:
        return jsonify({'error': '業種名は必須です'}), 400
    
    db = get_db()
    try:
        cursor = db.execute(
            'INSERT INTO industries (name, name_en, description, icon, color) VALUES (?, ?, ?, ?, ?)',
            (name, name_en, description, icon, color)
        )
        db.commit()
        return jsonify({'success': True, 'id': cursor.lastrowid, 'message': '業種を追加しました'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'この業種名は既に存在します'}), 400

# 業種更新
@app.route('/api/admin/industries/<int:industry_id>', methods=['PUT'])
@admin_required
def update_industry(industry_id):
    data = request.json
    name = data.get('name')
    name_en = data.get('name_en', '')
    description = data.get('description', '')
    icon = data.get('icon', 'bi-building')
    color = data.get('color', '#667eea')
    
    if not name:
        return jsonify({'error': '業種名は必須です'}), 400
    
    db = get_db()
    db.execute(
        'UPDATE industries SET name = ?, name_en = ?, description = ?, icon = ?, color = ? WHERE id = ?',
        (name, name_en, description, icon, color, industry_id)
    )
    db.commit()
    
    return jsonify({'success': True, 'message': '業種を更新しました'})

# 業種削除
@app.route('/api/admin/industries/<int:industry_id>', methods=['DELETE'])
@admin_required
def delete_industry(industry_id):
    db = get_db()
    
    # この業種に所属するユーザーがいるかチェック
    users = db.execute('SELECT COUNT(*) as count FROM users WHERE industry_id = ?', (industry_id,)).fetchone()
    if users['count'] > 0:
        return jsonify({'error': 'この業種に所属するユーザーがいるため削除できません'}), 400
    
    # アクセス制御を削除
    db.execute('DELETE FROM category_industry_access WHERE industry_id = ?', (industry_id,))
    
    # 業種を削除
    db.execute('DELETE FROM industries WHERE id = ?', (industry_id,))
    db.commit()
    
    return jsonify({'success': True, 'message': '業種を削除しました'})

# ========== ユーザー管理API ==========

# ユーザー作成
@app.route('/api/admin/users', methods=['POST'])
@admin_required
def create_user():
    import re
    
    # 有効なロール一覧
    VALID_ROLES = {'user', 'company_admin', 'super_admin'}
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    MIN_PASSWORD_LENGTH = 8
    
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    industry_id = data.get('industry_id')
    company_name = data.get('company_name', '')
    is_admin = data.get('is_admin', False)
    role = data.get('role', 'user')
    user_tenant_id = data.get('tenant_id')
    department_id = data.get('department_id')
    
    if not username or not email or not password:
        return jsonify({'error': 'ユーザー名、メール、パスワードは必須です'}), 400
    
    # メール形式バリデーション
    if not EMAIL_PATTERN.match(email):
        return jsonify({'error': 'メールアドレスの形式が不正です'}), 400
    
    # パスワード強度チェック
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'パスワードは{MIN_PASSWORD_LENGTH}文字以上必要です'}), 400
    
    # ロール値のバリデーション
    if role not in VALID_ROLES:
        return jsonify({'error': f'無効なロールです。有効な値: {", ".join(VALID_ROLES)}'}), 400
    
    # company_admin は自テナントのユーザーのみ作成可能
    current_role = session.get('role', 'user')
    current_tenant_id = session.get('tenant_id')
    if current_role == 'company_admin':
        user_tenant_id = current_tenant_id  # 強制的に自テナントに設定
        if role == 'super_admin':
            return jsonify({'error': 'super_admin権限は付与できません'}), 403
        if role == 'company_admin':
            return jsonify({'error': 'company_admin権限の付与はsuper_adminのみ可能です'}), 403
    
    db = get_db()
    
    # ユーザー名の重複チェック
    existing = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if existing:
        return jsonify({'error': 'このユーザー名は既に使用されています'}), 400
    
    # メールの重複チェック
    existing_email = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    if existing_email:
        return jsonify({'error': 'このメールアドレスは既に使用されています'}), 400
    
    # is_adminフラグとの互換性
    if role == 'super_admin':
        is_admin = True
    
    try:
        cursor = db.execute(
            '''INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (username, email, generate_password_hash(password), 
             industry_id if industry_id else None,
             user_tenant_id if user_tenant_id else None,
             department_id if department_id else None,
             company_name, role, 1 if is_admin else 0)
        )
        db.commit()
        return jsonify({'success': True, 'id': cursor.lastrowid, 'message': 'ユーザーを作成しました'})
    except sqlite3.IntegrityError as e:
        return jsonify({'error': f'ユーザーの作成に失敗しました: {str(e)}'}), 400

# ユーザー更新
@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    import re
    
    # 有効なロール一覧
    VALID_ROLES = {'user', 'company_admin', 'super_admin'}
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    MIN_PASSWORD_LENGTH = 8
    
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')  # 空の場合は更新しない
    industry_id = data.get('industry_id')
    company_name = data.get('company_name', '')
    is_admin = data.get('is_admin', False)
    role = data.get('role', 'user')
    user_tenant_id = data.get('tenant_id')
    department_id = data.get('department_id')
    
    if not username or not email:
        return jsonify({'error': 'ユーザー名とメールは必須です'}), 400
    
    # メール形式バリデーション
    if not EMAIL_PATTERN.match(email):
        return jsonify({'error': 'メールアドレスの形式が不正です'}), 400
    
    # パスワード強度チェック（パスワード変更時のみ）
    if password and len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'パスワードは{MIN_PASSWORD_LENGTH}文字以上必要です'}), 400
    
    # ロール値のバリデーション
    if role not in VALID_ROLES:
        return jsonify({'error': f'無効なロールです。有効な値: {", ".join(VALID_ROLES)}'}), 400
    
    # company_admin のテナント境界チェック
    current_role = session.get('role', 'user')
    current_tenant_id = session.get('tenant_id')
    if current_role == 'company_admin':
        # 自テナントのユーザーのみ編集可能
        db_check = get_db()
        target_user = db_check.execute('SELECT tenant_id FROM users WHERE id = ?', (user_id,)).fetchone()
        if target_user and target_user['tenant_id'] != current_tenant_id:
            return jsonify({'error': '他テナントのユーザーは編集できません'}), 403
        user_tenant_id = current_tenant_id
        if role == 'super_admin':
            return jsonify({'error': 'super_admin権限は付与できません'}), 403
        if role == 'company_admin':
            # company_adminが他のユーザーにcompany_admin権限を付与することを防止
            target_current = db_check.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
            if not target_current or target_current['role'] != 'company_admin':
                return jsonify({'error': 'company_admin権限の付与はsuper_adminのみ可能です'}), 403
    
    # is_adminフラグとの互換性
    if role == 'super_admin':
        is_admin = True
    
    db = get_db()
    
    # company_adminからのロール変更時、最後の管理者でないかチェック
    current_user = db.execute('SELECT role, tenant_id FROM users WHERE id = ?', (user_id,)).fetchone()
    if current_user and current_user['role'] == 'company_admin' and role != 'company_admin':
        if current_user['tenant_id']:
            admin_count = db.execute(
                'SELECT COUNT(*) as cnt FROM users WHERE tenant_id = ? AND role = ? AND id != ?',
                (current_user['tenant_id'], 'company_admin', user_id)
            ).fetchone()['cnt']
            if admin_count == 0:
                return jsonify({
                    'error': 'このテナントの最後の管理者のロールは変更できません。先に別の管理者を設定してください。'
                }), 400
    
    # ユーザー名の重複チェック（自分以外）
    existing = db.execute('SELECT id FROM users WHERE username = ? AND id != ?', (username, user_id)).fetchone()
    if existing:
        return jsonify({'error': 'このユーザー名は既に使用されています'}), 400
    
    # メールの重複チェック（自分以外）
    existing_email = db.execute('SELECT id FROM users WHERE email = ? AND id != ?', (email, user_id)).fetchone()
    if existing_email:
        return jsonify({'error': 'このメールアドレスは既に使用されています'}), 400
    
    try:
        if password:
            db.execute(
                '''UPDATE users SET username = ?, email = ?, password_hash = ?, 
                   industry_id = ?, tenant_id = ?, department_id = ?, company_name = ?, role = ?, is_admin = ? WHERE id = ?''',
                (username, email, generate_password_hash(password),
                 industry_id if industry_id else None,
                 user_tenant_id if user_tenant_id else None,
                 department_id if department_id else None,
                 company_name, role, 1 if is_admin else 0, user_id)
            )
        else:
            db.execute(
                '''UPDATE users SET username = ?, email = ?, 
                   industry_id = ?, tenant_id = ?, department_id = ?, company_name = ?, role = ?, is_admin = ? WHERE id = ?''',
                (username, email, industry_id if industry_id else None,
                 user_tenant_id if user_tenant_id else None,
                 department_id if department_id else None,
                 company_name, role, 1 if is_admin else 0, user_id)
            )
        db.commit()
        return jsonify({'success': True, 'message': 'ユーザーを更新しました'})
    except sqlite3.IntegrityError as e:
        return jsonify({'error': f'ユーザーの更新に失敗しました: {str(e)}'}), 400

# ユーザー削除
@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    # 自分自身は削除できない
    if user_id == session.get('user_id'):
        return jsonify({'error': '自分自身を削除することはできません'}), 400
    
    db = get_db()
    
    # ユーザーの存在確認
    user = db.execute('SELECT id, role, tenant_id FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        return jsonify({'error': 'ユーザーが見つかりません'}), 404
    
    # 最後のcompany_adminを削除しようとしていないかチェック
    if user['role'] == 'company_admin' and user['tenant_id']:
        admin_count = db.execute(
            'SELECT COUNT(*) as cnt FROM users WHERE tenant_id = ? AND role = ? AND id != ?',
            (user['tenant_id'], 'company_admin', user_id)
        ).fetchone()['cnt']
        if admin_count == 0:
            return jsonify({
                'error': 'このテナントの最後の管理者です。削除する前に別の管理者を設定してください。'
            }), 400
    
    # 視聴進捗を削除
    db.execute('DELETE FROM progress WHERE user_id = ?', (user_id,))
    
    # ユーザーを削除
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    
    return jsonify({'success': True, 'message': 'ユーザーを削除しました'})

# ユーザー詳細取得
@app.route('/api/admin/users/<int:user_id>')
@admin_required
def get_user(user_id):
    db = get_db()
    user = db.execute('''
        SELECT id, username, email, industry_id, tenant_id, department_id, company_name, role, is_admin
        FROM users WHERE id = ?
    ''', (user_id,)).fetchone()
    
    if not user:
        return jsonify({'error': 'ユーザーが見つかりません'}), 404
    
    return jsonify(dict(user))

# ========== テナント管理API ==========

@app.route('/api/admin/tenants')
@admin_required
def get_tenants():
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    
    if role == 'super_admin':
        tenants = db.execute('''
            SELECT t.*, i.name as industry_name,
                   (SELECT COUNT(*) FROM users WHERE tenant_id = t.id) as user_count,
                   (SELECT COUNT(*) FROM departments WHERE tenant_id = t.id) as dept_count
            FROM tenants t
            LEFT JOIN industries i ON t.industry_id = i.id
            ORDER BY t.name
        ''').fetchall()
    else:
        tenants = db.execute('''
            SELECT t.*, i.name as industry_name,
                   (SELECT COUNT(*) FROM users WHERE tenant_id = t.id) as user_count,
                   (SELECT COUNT(*) FROM departments WHERE tenant_id = t.id) as dept_count
            FROM tenants t
            LEFT JOIN industries i ON t.industry_id = i.id
            WHERE t.id = ?
        ''', (tenant_id,)).fetchall()
    
    return jsonify([dict(t) for t in tenants])

@app.route('/api/admin/tenants', methods=['POST'])
@role_required('super_admin')
def create_tenant():
    data = request.json
    name = data.get('name', '').strip()
    industry_id = data.get('industry_id')
    
    if not name:
        return jsonify({'error': 'テナント名は必須です'}), 400
    
    db = get_db()
    cursor = db.execute(
        'INSERT INTO tenants (name, industry_id) VALUES (?, ?)',
        (name, industry_id if industry_id else None)
    )
    db.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid, 'message': 'テナントを作成しました'})

@app.route('/api/admin/tenants/<int:tenant_id>', methods=['PUT'])
@role_required('super_admin')
def update_tenant(tenant_id):
    data = request.json
    name = data.get('name', '').strip()
    industry_id = data.get('industry_id')
    
    if not name:
        return jsonify({'error': 'テナント名は必須です'}), 400
    
    db = get_db()
    db.execute(
        'UPDATE tenants SET name = ?, industry_id = ? WHERE id = ?',
        (name, industry_id if industry_id else None, tenant_id)
    )
    db.commit()
    return jsonify({'success': True, 'message': 'テナントを更新しました'})

@app.route('/api/admin/tenants/<int:tenant_id>', methods=['DELETE'])
@role_required('super_admin')
def delete_tenant(tenant_id):
    db = get_db()
    users = db.execute('SELECT COUNT(*) as count FROM users WHERE tenant_id = ?', (tenant_id,)).fetchone()
    if users['count'] > 0:
        return jsonify({'error': 'このテナントに所属するユーザーがいるため削除できません'}), 400
    
    db.execute('DELETE FROM departments WHERE tenant_id = ?', (tenant_id,))
    db.execute('DELETE FROM tenants WHERE id = ?', (tenant_id,))
    db.commit()
    return jsonify({'success': True, 'message': 'テナントを削除しました'})

# テナント管理者チェックAPI
@app.route('/api/admin/tenants/health')
@admin_required
def tenant_health_check():
    """全テナントのcompany_admin有無をチェック"""
    db = get_db()
    tenants = db.execute('''
        SELECT t.id, t.name, i.name as industry_name,
               (SELECT COUNT(*) FROM users WHERE tenant_id = t.id) as user_count,
               (SELECT COUNT(*) FROM users WHERE tenant_id = t.id AND role = 'company_admin') as admin_count
        FROM tenants t
        LEFT JOIN industries i ON t.industry_id = i.id
        ORDER BY t.name
    ''').fetchall()
    
    results = []
    warnings = []
    for t in tenants:
        entry = dict(t)
        entry['has_admin'] = entry['admin_count'] > 0
        results.append(entry)
        if entry['user_count'] > 0 and entry['admin_count'] == 0:
            warnings.append(f"{entry['name']} にcompany_adminがいません")
    
    return jsonify({
        'tenants': results,
        'warnings': warnings,
        'all_healthy': len(warnings) == 0
    })

# ========== 部署管理API ==========

@app.route('/api/admin/departments')
@admin_required
def get_departments():
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    filter_tenant_id = request.args.get('tenant_id')
    
    if role == 'super_admin' and filter_tenant_id:
        departments = db.execute('''
            SELECT d.*, t.name as tenant_name,
                   (SELECT COUNT(*) FROM users WHERE department_id = d.id) as user_count
            FROM departments d
            JOIN tenants t ON d.tenant_id = t.id
            WHERE d.tenant_id = ?
            ORDER BY d.name
        ''', (filter_tenant_id,)).fetchall()
    elif role == 'super_admin':
        departments = db.execute('''
            SELECT d.*, t.name as tenant_name,
                   (SELECT COUNT(*) FROM users WHERE department_id = d.id) as user_count
            FROM departments d
            JOIN tenants t ON d.tenant_id = t.id
            ORDER BY t.name, d.name
        ''').fetchall()
    elif tenant_id:
        departments = db.execute('''
            SELECT d.*, t.name as tenant_name,
                   (SELECT COUNT(*) FROM users WHERE department_id = d.id) as user_count
            FROM departments d
            JOIN tenants t ON d.tenant_id = t.id
            WHERE d.tenant_id = ?
            ORDER BY d.name
        ''', (tenant_id,)).fetchall()
    else:
        departments = []
    
    return jsonify([dict(d) for d in departments])

@app.route('/api/admin/departments', methods=['POST'])
@admin_required
def create_department():
    data = request.json
    name = data.get('name', '').strip()
    dept_tenant_id = data.get('tenant_id')
    parent_department_id = data.get('parent_department_id')
    
    if not name:
        return jsonify({'error': '部署名は必須です'}), 400
    
    # company_admin は自テナントの部署のみ作成可能
    current_role = session.get('role', 'user')
    current_tenant_id = session.get('tenant_id')
    if current_role == 'company_admin':
        dept_tenant_id = current_tenant_id
    
    if not dept_tenant_id:
        return jsonify({'error': 'テナントIDは必須です'}), 400
    
    db = get_db()
    cursor = db.execute(
        'INSERT INTO departments (tenant_id, name, parent_department_id) VALUES (?, ?, ?)',
        (dept_tenant_id, name, parent_department_id if parent_department_id else None)
    )
    db.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid, 'message': '部署を作成しました'})

@app.route('/api/admin/departments/<int:dept_id>', methods=['PUT'])
@admin_required
def update_department(dept_id):
    data = request.json
    name = data.get('name', '').strip()
    parent_department_id = data.get('parent_department_id')
    
    if not name:
        return jsonify({'error': '部署名は必須です'}), 400
    
    # テナント境界チェック
    current_role = session.get('role', 'user')
    current_tenant_id = session.get('tenant_id')
    if current_role == 'company_admin':
        db = get_db()
        dept = db.execute('SELECT tenant_id FROM departments WHERE id = ?', (dept_id,)).fetchone()
        if not dept or dept['tenant_id'] != current_tenant_id:
            return jsonify({'error': '他テナントの部署は編集できません'}), 403
    
    db = get_db()
    db.execute(
        'UPDATE departments SET name = ?, parent_department_id = ? WHERE id = ?',
        (name, parent_department_id if parent_department_id else None, dept_id)
    )
    db.commit()
    return jsonify({'success': True, 'message': '部署を更新しました'})

@app.route('/api/admin/departments/<int:dept_id>', methods=['DELETE'])
@admin_required
def delete_department(dept_id):
    db = get_db()
    
    # テナント境界チェック
    current_role = session.get('role', 'user')
    current_tenant_id = session.get('tenant_id')
    if current_role == 'company_admin':
        dept = db.execute('SELECT tenant_id FROM departments WHERE id = ?', (dept_id,)).fetchone()
        if not dept or dept['tenant_id'] != current_tenant_id:
            return jsonify({'error': '他テナントの部署は削除できません'}), 403
    
    # 部署に所属するユーザーがいるかチェック
    users = db.execute('SELECT COUNT(*) as count FROM users WHERE department_id = ?', (dept_id,)).fetchone()
    if users['count'] > 0:
        return jsonify({'error': 'この部署に所属するユーザーがいるため削除できません'}), 400
    
    # 子部署があるかチェック
    children = db.execute('SELECT COUNT(*) as count FROM departments WHERE parent_department_id = ?', (dept_id,)).fetchone()
    if children['count'] > 0:
        return jsonify({'error': 'この部署に子部署があるため削除できません'}), 400
    
    db.execute('DELETE FROM departments WHERE id = ?', (dept_id,))
    db.commit()
    return jsonify({'success': True, 'message': '部署を削除しました'})

# ========== CSV一括ユーザー登録/出力 ==========

@app.route('/api/admin/users/export-csv')
@admin_required
def export_users_csv():
    """ユーザー一覧をCSVとして出力"""
    import csv
    import io
    
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    
    if role == 'super_admin':
        users = db.execute('''
            SELECT u.username, u.email, u.company_name, u.role, 
                   i.name as industry_name, t.name as tenant_name, d.name as department_name
            FROM users u
            LEFT JOIN industries i ON u.industry_id = i.id
            LEFT JOIN tenants t ON u.tenant_id = t.id
            LEFT JOIN departments d ON u.department_id = d.id
            ORDER BY u.id
        ''').fetchall()
    else:
        users = db.execute('''
            SELECT u.username, u.email, u.company_name, u.role,
                   i.name as industry_name, t.name as tenant_name, d.name as department_name
            FROM users u
            LEFT JOIN industries i ON u.industry_id = i.id
            LEFT JOIN tenants t ON u.tenant_id = t.id
            LEFT JOIN departments d ON u.department_id = d.id
            WHERE u.tenant_id = ?
            ORDER BY u.id
        ''', (tenant_id,)).fetchall()
    
    output = io.StringIO()
    output.write('\ufeff')  # BOM for Excel compatibility
    writer = csv.writer(output)
    writer.writerow(['ユーザー名', 'メール', '会社名', 'ロール', '業種', 'テナント', '部署'])
    
    for u in users:
        writer.writerow([
            u['username'], u['email'], u['company_name'] or '', u['role'] or 'user',
            u['industry_name'] or '', u['tenant_name'] or '', u['department_name'] or ''
        ])
    
    from flask import Response
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=users.csv'}
    )

@app.route('/api/admin/users/import-csv', methods=['POST'])
@admin_required
def import_users_csv():
    """CSVファイルからユーザーを一括登録"""
    import csv
    import io
    import re
    
    # 有効なロール一覧
    VALID_ROLES = {'user', 'company_admin', 'super_admin'}
    # メール形式の基本バリデーション
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    # パスワード最低文字数
    MIN_PASSWORD_LENGTH = 8
    
    if 'file' not in request.files:
        return jsonify({'error': 'CSVファイルが選択されていません'}), 400
    
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'CSVファイルのみ対応しています'}), 400
    
    current_role = session.get('role', 'user')
    current_tenant_id = session.get('tenant_id')
    
    try:
        content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        
        db = get_db()
        created = 0
        errors = []
        
        for i, row in enumerate(reader, start=2):  # ヘッダーの次から
            username = row.get('ユーザー名', '').strip()
            email = row.get('メール', '').strip()
            password = row.get('パスワード', '').strip()
            company_name = row.get('会社名', '').strip()
            role = row.get('ロール', 'user').strip()
            industry_name = row.get('業種', '').strip()
            tenant_name = row.get('テナント', '').strip()
            department_name = row.get('部署', '').strip()
            
            if not username or not email:
                errors.append(f'行{i}: ユーザー名またはメールが空です')
                continue
            
            # メール形式バリデーション
            if not EMAIL_PATTERN.match(email):
                errors.append(f'行{i}: メールアドレスの形式が不正です ({email})')
                continue
            
            # パスワードバリデーション
            if not password:
                errors.append(f'行{i}: パスワードが空です')
                continue
            if len(password) < MIN_PASSWORD_LENGTH:
                errors.append(f'行{i}: パスワードは{MIN_PASSWORD_LENGTH}文字以上必要です')
                continue
            
            # ロール値のバリデーション
            if role not in VALID_ROLES:
                errors.append(f'行{i}: 無効なロールです ({role})。有効な値: user, company_admin, super_admin')
                continue
            
            # 重複チェック
            existing = db.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
            if existing:
                errors.append(f'行{i}: {username} は既に存在します')
                continue
            
            # company_admin の権限エスカレーション防止
            if current_role == 'company_admin':
                if role == 'super_admin':
                    errors.append(f'行{i}: super_admin権限は付与できません')
                    continue
                if role == 'company_admin':
                    errors.append(f'行{i}: company_admin権限の付与はsuper_adminのみ可能です')
                    continue
            
            # 業種IDを解決
            industry_id = None
            if industry_name:
                ind = db.execute('SELECT id FROM industries WHERE name = ?', (industry_name,)).fetchone()
                if ind:
                    industry_id = ind['id']
            
            # テナントIDを解決
            user_tenant_id = None
            if current_role == 'company_admin':
                user_tenant_id = current_tenant_id
            elif tenant_name:
                t = db.execute('SELECT id FROM tenants WHERE name = ?', (tenant_name,)).fetchone()
                if t:
                    user_tenant_id = t['id']
            
            # 部署IDを解決
            department_id = None
            if department_name and user_tenant_id:
                d = db.execute('SELECT id FROM departments WHERE name = ? AND tenant_id = ?', 
                             (department_name, user_tenant_id)).fetchone()
                if d:
                    department_id = d['id']
            
            db.execute(
                '''INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (username, email, generate_password_hash(password),
                 industry_id, user_tenant_id, department_id,
                 company_name, role, 1 if role == 'super_admin' else 0)
            )
            created += 1
        
        db.commit()
        
        result = {'success': True, 'created': created, 'message': f'{created}件のユーザーを作成しました'}
        if errors:
            result['errors'] = errors
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'CSV処理エラー: {str(e)}'}), 500

# ========== 個人別視聴統計の拡張 ==========

@app.route('/api/admin/user-stats-detail/<int:user_id>')
@admin_required
def user_stats_detail(user_id):
    """ユーザーの詳細な視聴統計（累計時間、完了率、フィルタリング対応）"""
    db = get_db()
    
    # テナント境界チェック
    current_role = session.get('role', 'user')
    current_tenant_id = session.get('tenant_id')
    if current_role == 'company_admin':
        target_user = db.execute('SELECT tenant_id FROM users WHERE id = ?', (user_id,)).fetchone()
        if not target_user or target_user['tenant_id'] != current_tenant_id:
            return jsonify({'error': '他テナントのユーザーの統計は参照できません'}), 403
    
    # ユーザー基本情報
    user_info = db.execute('''
        SELECT u.id, u.username, u.email, u.company_name, u.role,
               i.name as industry_name, t.name as tenant_name, d.name as department_name
        FROM users u
        LEFT JOIN industries i ON u.industry_id = i.id
        LEFT JOIN tenants t ON u.tenant_id = t.id
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE u.id = ?
    ''', (user_id,)).fetchone()
    
    if not user_info:
        return jsonify({'error': 'ユーザーが見つかりません'}), 404
    
    # 視聴進捗の詳細
    stats = db.execute('''
        SELECT v.id, v.title, v.slug, c.name as category_name,
               p.progress_percent, p.last_position, p.updated_at
        FROM videos v
        LEFT JOIN progress p ON v.id = p.video_id AND p.user_id = ?
        LEFT JOIN categories c ON v.category_id = c.id
        ORDER BY p.updated_at DESC NULLS LAST
    ''', (user_id,)).fetchall()
    
    # 集計統計
    total_videos = len(stats)
    viewed_videos = sum(1 for s in stats if s['progress_percent'] and s['progress_percent'] > 0)
    completed_videos = sum(1 for s in stats if s['progress_percent'] and s['progress_percent'] >= 90)
    total_watch_time_seconds = sum(s['last_position'] or 0 for s in stats)
    avg_progress = sum(s['progress_percent'] or 0 for s in stats) / total_videos if total_videos > 0 else 0
    
    return jsonify({
        'user': dict(user_info),
        'summary': {
            'total_videos': total_videos,
            'viewed_videos': viewed_videos,
            'completed_videos': completed_videos,
            'completion_rate': round(completed_videos / total_videos * 100, 1) if total_videos > 0 else 0,
            'total_watch_time_seconds': round(total_watch_time_seconds),
            'total_watch_time_display': f'{int(total_watch_time_seconds // 3600)}h {int((total_watch_time_seconds % 3600) // 60)}m',
            'avg_progress': round(avg_progress, 1)
        },
        'details': [dict(s) for s in stats]
    })

@app.route('/api/admin/department-stats')
@admin_required
def department_stats():
    """部署別の視聴統計"""
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    filter_tenant_id = request.args.get('tenant_id', tenant_id)
    
    if role != 'super_admin':
        filter_tenant_id = tenant_id  # company_admin は自テナントのみ
    
    if not filter_tenant_id:
        return jsonify([])
    
    departments = db.execute('''
        SELECT d.id, d.name,
               COUNT(DISTINCT u.id) as user_count,
               COALESCE(AVG(p.progress_percent), 0) as avg_progress,
               COUNT(CASE WHEN p.progress_percent >= 90 THEN 1 END) as completed_count,
               COUNT(p.id) as total_views
        FROM departments d
        LEFT JOIN users u ON u.department_id = d.id
        LEFT JOIN progress p ON p.user_id = u.id
        WHERE d.tenant_id = ?
        GROUP BY d.id, d.name
        ORDER BY d.name
    ''', (filter_tenant_id,)).fetchall()
    
    return jsonify([dict(d) for d in departments])

# ========== カスタムアクセスログ ==========

@app.before_request
def log_access():
    """全リクエストのアクセスログを記録"""
    # 静的ファイルやAPIヘルスチェックは除外
    if request.path.startswith('/static') or request.path == '/favicon.ico':
        return
    
    request._start_time = datetime.now()

@app.after_request
def save_access_log(response):
    """リクエスト完了後にアクセスログを保存"""
    # 静的ファイルは除外
    if request.path.startswith('/static') or request.path == '/favicon.ico':
        return response
    
    try:
        start_time = getattr(request, '_start_time', None)
        duration_ms = None
        if start_time:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        user_id = session.get('user_id')
        tenant_id = session.get('tenant_id')
        
        db = get_db()
        db.execute('''
            INSERT INTO access_logs (user_id, tenant_id, path, method, status_code, user_agent, ip_address, referrer, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, tenant_id,
            request.path, request.method, response.status_code,
            str(request.user_agent)[:500] if request.user_agent else None,
            request.remote_addr,
            request.referrer[:500] if request.referrer else None,
            duration_ms
        ))
        db.commit()
    except Exception:
        pass  # アクセスログの記録失敗は無視
    
    return response

# ========== マイ視聴状況（一般ユーザー向け） ==========

@app.route('/my-progress')
@login_required
def my_progress_page():
    return render_template('my_progress.html')

@app.route('/api/my-progress')
@login_required
def my_progress_api():
    """ログインユーザー自身の視聴進捗データ"""
    db = get_db()
    user_id = session['user_id']
    industry_id = session.get('industry_id')
    is_admin = session.get('is_admin', False)
    
    # 業種ベースのカテゴリーアクセス制御で対象動画を取得
    accessible_category_ids = get_accessible_category_ids(db, industry_id, is_admin)
    
    if accessible_category_ids:
        placeholders = ','.join('?' * len(accessible_category_ids))
        videos = db.execute(f'''
            SELECT v.id, v.title, v.description, c.id as category_id, c.name as category_name,
                   c.icon as category_icon, c.color as category_color,
                   pc.name as parent_category_name
            FROM videos v
            LEFT JOIN categories c ON v.category_id = c.id
            LEFT JOIN categories pc ON c.parent_id = pc.id
            WHERE v.category_id IN ({placeholders})
               OR v.category_id IS NULL
            ORDER BY c.display_order, c.name, v.created_at
        ''', accessible_category_ids).fetchall()
    else:
        videos = db.execute('''
            SELECT v.id, v.title, v.description, c.id as category_id, c.name as category_name,
                   c.icon as category_icon, c.color as category_color,
                   pc.name as parent_category_name
            FROM videos v
            LEFT JOIN categories c ON v.category_id = c.id
            LEFT JOIN categories pc ON c.parent_id = pc.id
            WHERE v.category_id IS NULL
            ORDER BY v.created_at
        ''').fetchall()
    
    video_list = [dict(v) for v in videos]
    total_videos = len(video_list)
    accessible_video_ids = {v['id'] for v in video_list}
    
    # ユーザー自身の進捗データを取得
    progress_rows = db.execute('''
        SELECT p.video_id, p.progress_percent, p.last_position, p.updated_at
        FROM progress p
        WHERE p.user_id = ?
    ''', [user_id]).fetchall()
    
    # 進捗マップを構築（アクセス可能な動画のみ）
    progress_map = {}
    for p in progress_rows:
        if p['video_id'] in accessible_video_ids:
            progress_map[p['video_id']] = {
                'progress_percent': p['progress_percent'],
                'last_position': p['last_position'],
                'updated_at': p['updated_at']
            }
    
    # 統計計算
    videos_started = len(progress_map)
    videos_completed = sum(1 for vp in progress_map.values() if vp['progress_percent'] >= 90)
    total_progress = sum(vp['progress_percent'] for vp in progress_map.values())
    avg_progress = round(total_progress / total_videos, 1) if total_videos > 0 else 0
    
    # 動画リストに進捗情報を付加
    video_details = []
    for v in video_list:
        vp = progress_map.get(v['id'])
        if vp:
            status = 'completed' if vp['progress_percent'] >= 90 else 'in_progress'
        else:
            status = 'not_started'
        
        video_details.append({
            **v,
            'progress_percent': vp['progress_percent'] if vp else 0,
            'last_position': vp['last_position'] if vp else 0,
            'updated_at': vp['updated_at'] if vp else None,
            'started_at': vp['updated_at'] if vp else None,
            'status': status
        })
    
    # カテゴリー別の集計
    category_stats = {}
    for v in video_details:
        cat_name = v.get('parent_category_name') or v.get('category_name') or '未分類'
        if cat_name not in category_stats:
            category_stats[cat_name] = {
                'total': 0,
                'started': 0,
                'completed': 0,
                'total_progress': 0
            }
        category_stats[cat_name]['total'] += 1
        if v['status'] != 'not_started':
            category_stats[cat_name]['started'] += 1
        if v['status'] == 'completed':
            category_stats[cat_name]['completed'] += 1
        category_stats[cat_name]['total_progress'] += v['progress_percent']
    
    category_summary = []
    for name, stats in category_stats.items():
        category_summary.append({
            'name': name,
            'total': stats['total'],
            'started': stats['started'],
            'completed': stats['completed'],
            'avg_progress': round(stats['total_progress'] / stats['total'], 1) if stats['total'] > 0 else 0
        })
    
    # 最近の視聴アクティビティ（直近の進捗更新）
    recent_activity = sorted(
        [v for v in video_details if v['updated_at']],
        key=lambda x: x['updated_at'],
        reverse=True
    )[:5]
    
    return jsonify({
        'summary': {
            'total_videos': total_videos,
            'videos_started': videos_started,
            'videos_completed': videos_completed,
            'avg_progress': avg_progress,
            'all_completed': total_videos > 0 and videos_completed >= total_videos
        },
        'videos': video_details,
        'category_stats': category_summary,
        'recent_activity': recent_activity
    })

# ========== ユーザー視聴状況ダッシュボード（管理者向け） ==========

@app.route('/admin/user-progress')
@admin_required
def user_progress_dashboard():
    return render_template('user_progress.html')

@app.route('/api/admin/user-progress')
@admin_required
def user_progress_api():
    """ユーザー×動画の視聴進捗マトリクスデータ"""
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    industry_id = session.get('industry_id')
    
    # テナント境界フィルタリング
    user_filter = ""
    user_params = []
    if role != 'super_admin' and tenant_id:
        user_filter = "WHERE u.tenant_id = ?"
        user_params = [tenant_id]
    
    # 対象ユーザー一覧を取得
    users = db.execute(f'''
        SELECT u.id, u.username, u.company_name, u.department_id,
               d.name as department_name
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        {user_filter}
        ORDER BY d.name, u.username
    ''', user_params).fetchall()
    
    # 業種ベースのカテゴリーアクセス制御で動画をフィルタリング
    if role == 'super_admin':
        # super_admin は全動画を表示
        videos = db.execute('''
            SELECT v.id, v.title, c.name as category_name
            FROM videos v
            LEFT JOIN categories c ON v.category_id = c.id
            ORDER BY c.display_order, v.created_at
        ''').fetchall()
    else:
        # company_admin は自業種がアクセス可能なカテゴリーの動画のみ表示
        accessible_category_ids = get_accessible_category_ids(db, industry_id, is_admin=False)
        if accessible_category_ids:
            placeholders = ','.join('?' * len(accessible_category_ids))
            videos = db.execute(f'''
                SELECT v.id, v.title, c.name as category_name
                FROM videos v
                LEFT JOIN categories c ON v.category_id = c.id
                WHERE v.category_id IN ({placeholders})
                   OR v.category_id IS NULL
                ORDER BY c.display_order, v.created_at
            ''', accessible_category_ids).fetchall()
        else:
            # アクセス可能なカテゴリーがない場合はカテゴリー未設定の動画のみ
            videos = db.execute('''
                SELECT v.id, v.title, c.name as category_name
                FROM videos v
                LEFT JOIN categories c ON v.category_id = c.id
                WHERE v.category_id IS NULL
                ORDER BY c.display_order, v.created_at
            ''').fetchall()
    
    video_list = [dict(v) for v in videos]
    total_videos = len(video_list)
    
    # アクセス可能な動画IDセットを作成（進捗フィルタリング用）
    accessible_video_ids = {v['id'] for v in video_list}
    
    # 全ユーザーの進捗データを一括取得
    if role != 'super_admin' and tenant_id:
        progress_rows = db.execute('''
            SELECT p.user_id, p.video_id, p.progress_percent, p.last_position, p.updated_at
            FROM progress p
            JOIN users u ON p.user_id = u.id
            WHERE u.tenant_id = ?
        ''', [tenant_id]).fetchall()
    else:
        progress_rows = db.execute('''
            SELECT p.user_id, p.video_id, p.progress_percent, p.last_position, p.updated_at
            FROM progress p
        ''').fetchall()
    
    # 進捗データをユーザーID -> {動画ID -> 進捗} のマップに変換
    # ※アクセス可能な動画の進捗のみを含める
    progress_map = {}
    for p in progress_rows:
        if p['video_id'] not in accessible_video_ids:
            continue  # アクセス不可な動画の進捗はスキップ
        uid = p['user_id']
        if uid not in progress_map:
            progress_map[uid] = {}
        progress_map[uid][p['video_id']] = {
            'progress_percent': p['progress_percent'],
            'last_position': p['last_position'],
            'updated_at': p['updated_at']
        }
    
    # ユーザーデータを構築
    user_list = []
    for user in users:
        uid = user['id']
        user_progress = progress_map.get(uid, {})
        
        # 統計計算
        videos_started = len(user_progress)
        videos_completed = sum(1 for vp in user_progress.values() if vp['progress_percent'] >= 90)
        
        if total_videos > 0:
            # 全動画に対する平均進捗（未視聴=0%として計算）
            total_progress = sum(vp['progress_percent'] for vp in user_progress.values())
            avg_progress = total_progress / total_videos
        else:
            avg_progress = 0
        
        all_completed = total_videos > 0 and videos_completed >= total_videos
        
        user_list.append({
            'id': uid,
            'username': user['username'],
            'company_name': user['company_name'],
            'department_id': user['department_id'],
            'department_name': user['department_name'],
            'video_progress': {vid: vp for vid, vp in user_progress.items()},
            'videos_started': videos_started,
            'videos_completed': videos_completed,
            'avg_progress': round(avg_progress, 1),
            'all_completed': all_completed
        })
    
    # 部署一覧
    if role != 'super_admin' and tenant_id:
        departments = db.execute(
            'SELECT id, name FROM departments WHERE tenant_id = ? ORDER BY name', [tenant_id]
        ).fetchall()
    else:
        departments = db.execute('SELECT id, name FROM departments ORDER BY name').fetchall()
    
    return jsonify({
        'users': user_list,
        'videos': video_list,
        'departments': [dict(d) for d in departments],
        'total_videos': total_videos
    })

# ========== アクセス分析ダッシュボード ==========

@app.route('/admin/analytics')
@admin_required
def analytics_dashboard():
    return render_template('analytics.html')

@app.route('/api/admin/analytics/summary')
@admin_required
def analytics_summary():
    """アクセス分析の集計データ"""
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    
    days = request.args.get('days', 30, type=int)
    
    # テナント境界フィルタリング
    tenant_filter = ""
    params = [days]
    if role != 'super_admin' and tenant_id:
        tenant_filter = "AND tenant_id = ?"
        params.append(tenant_id)
    
    # 日別アクセス数
    daily = db.execute(f'''
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM access_logs
        WHERE created_at >= datetime('now', '-' || ? || ' days') {tenant_filter}
        GROUP BY DATE(created_at)
        ORDER BY date
    ''', params).fetchall()
    
    # ページ別アクセス数
    pages = db.execute(f'''
        SELECT path, COUNT(*) as count, AVG(duration_ms) as avg_duration
        FROM access_logs
        WHERE created_at >= datetime('now', '-' || ? || ' days') {tenant_filter}
          AND method = 'GET' AND status_code = 200
        GROUP BY path
        ORDER BY count DESC
        LIMIT 20
    ''', params).fetchall()
    
    # ユーザー別アクセス数
    user_access = db.execute(f'''
        SELECT u.username, u.company_name, COUNT(al.id) as access_count,
               MAX(al.created_at) as last_access
        FROM access_logs al
        JOIN users u ON al.user_id = u.id
        WHERE al.created_at >= datetime('now', '-' || ? || ' days') {tenant_filter}
        GROUP BY al.user_id
        ORDER BY access_count DESC
        LIMIT 20
    ''', params).fetchall()
    
    # 総アクセス数
    total = db.execute(f'''
        SELECT COUNT(*) as total,
               COUNT(DISTINCT user_id) as unique_users,
               AVG(duration_ms) as avg_duration
        FROM access_logs
        WHERE created_at >= datetime('now', '-' || ? || ' days') {tenant_filter}
    ''', params).fetchone()
    
    return jsonify({
        'daily': [dict(d) for d in daily],
        'pages': [dict(p) for p in pages],
        'user_access': [dict(u) for u in user_access],
        'total': dict(total) if total else {}
    })

# ========== 動画視聴分析ダッシュボード ==========

@app.route('/admin/video-analytics')
@admin_required
def video_analytics_dashboard():
    return render_template('video_analytics.html')

@app.route('/api/admin/video-analytics/summary')
@admin_required
def video_analytics_summary():
    """動画視聴状況の集計データ"""
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    industry_id = session.get('industry_id')
    
    # テナント境界フィルタリング
    user_filter = ""
    user_params = []
    if role != 'super_admin' and tenant_id:
        user_filter = "AND u.tenant_id = ?"
        user_params = [tenant_id]
    
    # 業種ベースのカテゴリーアクセス制御
    video_category_filter = ""
    video_category_params = []
    if role != 'super_admin':
        accessible_category_ids = get_accessible_category_ids(db, industry_id, is_admin=False)
        if accessible_category_ids:
            placeholders = ','.join('?' * len(accessible_category_ids))
            video_category_filter = f"WHERE (v.category_id IN ({placeholders}) OR v.category_id IS NULL)"
            video_category_params = list(accessible_category_ids)
        else:
            video_category_filter = "WHERE v.category_id IS NULL"
    
    # --- 1) 動画別の視聴統計 ---
    if role != 'super_admin' and tenant_id:
        # company_admin: 自テナントのユーザーの視聴データのみ集計 + 業種フィルタリング
        # パラメータ順: tenant_id (サブクエリ用) → category_ids (WHERE用)
        query_params = [tenant_id] + video_category_params
        video_stats = db.execute(f'''
            SELECT v.id, v.title, c.name as category_name,
                   COUNT(DISTINCT p.user_id) as viewer_count,
                   COALESCE(AVG(p.progress_percent), 0) as avg_progress,
                   COUNT(CASE WHEN p.progress_percent >= 90 THEN 1 END) as completed_count,
                   COALESCE(SUM(p.last_position), 0) as total_watch_seconds
            FROM videos v
            LEFT JOIN categories c ON v.category_id = c.id
            LEFT JOIN (
                SELECT p2.* FROM progress p2
                JOIN users u2 ON p2.user_id = u2.id
                WHERE u2.tenant_id = ?
            ) p ON v.id = p.video_id
            {video_category_filter}
            GROUP BY v.id, v.title, c.name
            ORDER BY viewer_count DESC
        ''', query_params).fetchall()
    else:
        # super_admin: 全データ
        video_stats = db.execute('''
            SELECT v.id, v.title, c.name as category_name,
                   COUNT(DISTINCT p.user_id) as viewer_count,
                   COALESCE(AVG(p.progress_percent), 0) as avg_progress,
                   COUNT(CASE WHEN p.progress_percent >= 90 THEN 1 END) as completed_count,
                   COALESCE(SUM(p.last_position), 0) as total_watch_seconds
            FROM videos v
            LEFT JOIN categories c ON v.category_id = c.id
            LEFT JOIN progress p ON v.id = p.video_id
            GROUP BY v.id, v.title, c.name
            ORDER BY viewer_count DESC
        ''').fetchall()
    
    # --- 2) ユーザー別の視聴統計（Top 20）---
    user_stats = db.execute(f'''
        SELECT u.id, u.username, u.company_name,
               d.name as department_name,
               COUNT(DISTINCT p.video_id) as videos_watched,
               COUNT(CASE WHEN p.progress_percent >= 90 THEN 1 END) as videos_completed,
               COALESCE(AVG(p.progress_percent), 0) as avg_progress,
               COALESCE(SUM(p.last_position), 0) as total_watch_seconds
        FROM users u
        LEFT JOIN progress p ON u.id = p.user_id
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE u.role != 'super_admin' {user_filter}
        GROUP BY u.id, u.username, u.company_name, d.name
        HAVING videos_watched > 0
        ORDER BY videos_completed DESC, avg_progress DESC
        LIMIT 20
    ''', user_params).fetchall()
    
    # --- 3) 部署別の視聴統計 ---
    dept_filter_params = []
    dept_filter = ""
    if role != 'super_admin' and tenant_id:
        dept_filter = "WHERE d.tenant_id = ?"
        dept_filter_params = [tenant_id]
    
    dept_stats = db.execute(f'''
        SELECT d.id, d.name as department_name, t.name as tenant_name,
               COUNT(DISTINCT u.id) as user_count,
               COALESCE(AVG(p.progress_percent), 0) as avg_progress,
               COUNT(CASE WHEN p.progress_percent >= 90 THEN 1 END) as completed_count,
               COUNT(DISTINCT p.video_id) as videos_watched
        FROM departments d
        JOIN tenants t ON d.tenant_id = t.id
        LEFT JOIN users u ON u.department_id = d.id
        LEFT JOIN progress p ON p.user_id = u.id
        {dept_filter}
        GROUP BY d.id, d.name, t.name
        ORDER BY avg_progress DESC
    ''', dept_filter_params).fetchall()
    
    # --- 4) 日別の視聴アクティビティ ---
    days = request.args.get('days', 30, type=int)
    daily_params = [days] + user_params
    daily_activity = db.execute(f'''
        SELECT DATE(p.updated_at) as date,
               COUNT(DISTINCT p.user_id) as active_users,
               COUNT(*) as view_events
        FROM progress p
        JOIN users u ON p.user_id = u.id
        WHERE p.updated_at >= datetime('now', '-' || ? || ' days')
              {user_filter}
        GROUP BY DATE(p.updated_at)
        ORDER BY date
    ''', daily_params).fetchall()
    
    # --- 5) サマリー統計 ---
    # 業種フィルタリング適用済みの動画数をカウント
    if video_category_params:
        placeholders = ','.join('?' * len(video_category_params))
        total_videos = db.execute(f'''
            SELECT COUNT(*) FROM videos
            WHERE category_id IN ({placeholders}) OR category_id IS NULL
        ''', video_category_params).fetchone()[0]
    elif video_category_filter:
        # カテゴリー未設定の動画のみ
        total_videos = db.execute('SELECT COUNT(*) FROM videos WHERE category_id IS NULL').fetchone()[0]
    else:
        total_videos = db.execute('SELECT COUNT(*) FROM videos').fetchone()[0]
    
    # 進捗統計もアクセス可能な動画のみ対象
    if video_category_params:
        placeholders = ','.join('?' * len(video_category_params))
        # パラメータ順: category_ids (WHERE IN用) → tenant_id (AND条件用)
        summary_params = video_category_params + user_params
        total_summary = db.execute(f'''
            SELECT COUNT(DISTINCT p.user_id) as total_viewers,
                   COALESCE(AVG(p.progress_percent), 0) as overall_avg_progress,
                   COUNT(CASE WHEN p.progress_percent >= 90 THEN 1 END) as total_completions,
                   COUNT(DISTINCT p.video_id) as videos_with_views
            FROM progress p
            JOIN users u ON p.user_id = u.id
            JOIN videos v ON p.video_id = v.id
            WHERE (v.category_id IN ({placeholders}) OR v.category_id IS NULL) {user_filter}
        ''', summary_params).fetchone()
    else:
        total_summary = db.execute(f'''
            SELECT COUNT(DISTINCT p.user_id) as total_viewers,
                   COALESCE(AVG(p.progress_percent), 0) as overall_avg_progress,
                   COUNT(CASE WHEN p.progress_percent >= 90 THEN 1 END) as total_completions,
                   COUNT(DISTINCT p.video_id) as videos_with_views
            FROM progress p
            JOIN users u ON p.user_id = u.id
            WHERE 1=1 {user_filter}
        ''', user_params).fetchone()
    
    # 全体完了率: 完了数 / (対象ユーザー数 × 全動画数)
    total_viewers = total_summary['total_viewers'] or 0
    total_completions = total_summary['total_completions'] or 0
    overall_completion_rate = 0
    if total_viewers > 0 and total_videos > 0:
        overall_completion_rate = round(total_completions / (total_viewers * total_videos) * 100, 1)
    
    return jsonify({
        'summary': {
            'total_videos': total_videos,
            'total_viewers': total_viewers,
            'overall_avg_progress': round(total_summary['overall_avg_progress'] or 0, 1),
            'overall_completion_rate': overall_completion_rate,
            'total_completions': total_completions,
            'videos_with_views': total_summary['videos_with_views'] or 0
        },
        'video_stats': [dict(v) for v in video_stats],
        'user_stats': [{
            **dict(u),
            'total_watch_display': f'{int(u["total_watch_seconds"] // 3600)}h {int((u["total_watch_seconds"] % 3600) // 60)}m'
        } for u in user_stats],
        'dept_stats': [dict(d) for d in dept_stats],
        'daily_activity': [dict(d) for d in daily_activity]
    })

# ========== AIチャット機能 ==========

# チャットページ
@app.route('/chat')
@login_required
def chat_page():
    return render_template('chat.html')

# ユースケース一覧取得API
@app.route('/api/chat/usecases')
@login_required
def get_chat_usecases():
    db = get_db()
    industry_id = session.get('industry_id')
    
    if industry_id:
        # ユーザーの業種に対応するユースケースを取得
        usecases = db.execute('''
            SELECT id, title, description, keywords, example_prompt
            FROM industry_usecases
            WHERE industry_id = ?
            ORDER BY id
        ''', (industry_id,)).fetchall()
    else:
        # 管理者等、業種未設定の場合は全ユースケースから一部を取得
        usecases = db.execute('''
            SELECT iu.id, iu.title, iu.description, iu.keywords, iu.example_prompt, i.name as industry_name
            FROM industry_usecases iu
            JOIN industries i ON iu.industry_id = i.id
            ORDER BY RANDOM()
            LIMIT 6
        ''').fetchall()
    
    return jsonify([dict(u) for u in usecases])

# チャット履歴取得API
@app.route('/api/chat/history')
@login_required
def get_chat_history():
    """ユーザーのチャット履歴を取得"""
    db = get_db()
    user_id = session['user_id']
    
    # 最新50件の履歴を取得
    history = db.execute('''
        SELECT id, message, response, recommended_videos, created_at
        FROM chat_history
        WHERE user_id = ?
        ORDER BY created_at ASC
        LIMIT 50
    ''', (user_id,)).fetchall()
    
    result = []
    for h in history:
        item = {
            'id': h['id'],
            'message': h['message'],
            'response': h['response'],
            'created_at': h['created_at']
        }
        # 推薦動画を復元
        if h['recommended_videos']:
            try:
                video_ids = json.loads(h['recommended_videos'])
                videos = []
                for vid in video_ids:
                    v = db.execute('SELECT id, title, slug FROM videos WHERE id = ?', (vid,)).fetchone()
                    if v:
                        videos.append({'id': v['id'], 'title': v['title'], 'slug': v['slug']})
                item['recommended_videos'] = videos
            except:
                item['recommended_videos'] = []
        else:
            item['recommended_videos'] = []
        result.append(item)
    
    return jsonify(result)

# RAG検索: ビデオと説明から関連コンテンツを検索
def extract_keywords(text):
    """日本語・英語のテキストからキーワードを抽出"""
    # 日本語の助詞・助動詞・記号を削除してキーワードを抽出
    stopwords = {'の', 'は', 'が', 'を', 'に', 'で', 'と', 'も', 'や', 'か', 'から', 'まで', 'より', 
                 'など', 'について', 'という', 'ような', 'どのような', 'ありますか', 'ですか', 
                 'ください', 'できますか', 'でしょうか', 'ものが', 'こと', 'もの', 'ます', 'です',
                 'どう', 'なに', 'どこ', 'いつ', 'だれ', 'なぜ', 'どれ', 'する', 'ある', 'いる',
                 'これ', 'それ', 'あれ', 'この', 'その', 'あの', 'ここ', 'そこ', 'あそこ',
                 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
                 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
                 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    
    # 記号・句読点・助詞で分割
    tokens = re.split(r'[\s、。！？!?・,.\-\(\)（）「」『』\[\]【】のはがをにでともやか]+', text.lower())
    
    # 2文字以上のキーワードを抽出
    keywords = []
    for token in tokens:
        token = token.strip()
        if len(token) >= 2 and token not in stopwords:
            keywords.append(token)
    
    # 重要なキーワードを優先（長いものを先に）
    keywords.sort(key=len, reverse=True)
    
    return keywords[:8]  # 最大8キーワード

def search_relevant_content(db, question, industry_id, is_admin=False):
    """質問に関連するコンテンツを検索（業種別アクセス制御付き）"""
    keywords = extract_keywords(question)
    
    # アクセス可能なカテゴリーIDを取得（業種別アクセス制御）
    accessible_category_ids = get_accessible_category_ids(db, industry_id, is_admin)
    
    # ビデオを検索（タイトルと説明文）- アクセス制御適用
    videos = []
    for keyword in keywords[:5]:  # 最初の5キーワードで検索
        if accessible_category_ids:
            # アクセス可能なカテゴリーの動画のみ検索
            placeholders = ','.join('?' * len(accessible_category_ids))
            search_results = db.execute(f'''
                SELECT DISTINCT v.id, v.title, v.description, c.name as category_name
                FROM videos v
                LEFT JOIN categories c ON v.category_id = c.id
                WHERE (LOWER(v.title) LIKE ? OR LOWER(v.description) LIKE ?)
                AND (v.category_id IS NULL OR v.category_id IN ({placeholders}))
                LIMIT 5
            ''', (f'%{keyword}%', f'%{keyword}%', *accessible_category_ids)).fetchall()
        else:
            # アクセス可能なカテゴリーがない場合は空
            search_results = []
        videos.extend([dict(v) for v in search_results])
    
    # 重複を除去
    seen_ids = set()
    unique_videos = []
    for v in videos:
        if v['id'] not in seen_ids:
            seen_ids.add(v['id'])
            unique_videos.append(v)
    
    # トランスクリプトを検索（アクセス制御適用）
    transcripts = []
    for keyword in keywords[:3]:
        if accessible_category_ids:
            placeholders = ','.join('?' * len(accessible_category_ids))
            transcript_results = db.execute(f'''
                SELECT vt.content, v.id as video_id, v.title as video_title
                FROM video_transcripts vt
                JOIN videos v ON vt.video_id = v.id
                LEFT JOIN categories c ON v.category_id = c.id
                WHERE LOWER(vt.content) LIKE ?
                AND (v.category_id IS NULL OR v.category_id IN ({placeholders}))
                LIMIT 3
            ''', (f'%{keyword}%', *accessible_category_ids)).fetchall()
        else:
            transcript_results = []
        transcripts.extend([dict(t) for t in transcript_results])
    
    # ユースケースを検索
    usecases = []
    if industry_id:
        for keyword in keywords[:3]:
            usecase_results = db.execute('''
                SELECT title, description, example_prompt
                FROM industry_usecases
                WHERE industry_id = ? AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(keywords) LIKE ?)
                LIMIT 3
            ''', (industry_id, f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')).fetchall()
            usecases.extend([dict(u) for u in usecase_results])
    
    # 外部ナレッジを検索（業種別）
    knowledge = []
    try:
        # テーブルが存在するか確認
        db.execute("SELECT 1 FROM external_knowledge LIMIT 1").fetchone()
        
        for keyword in keywords[:5]:
            if industry_id:
                # ユーザーの業種に関連するナレッジを検索
                knowledge_results = db.execute('''
                    SELECT DISTINCT title, content, source_file, keywords
                    FROM external_knowledge
                    WHERE industry_id = ? 
                    AND (LOWER(title) LIKE ? OR LOWER(content) LIKE ? OR LOWER(keywords) LIKE ?)
                    LIMIT 3
                ''', (industry_id, f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')).fetchall()
            elif is_admin:
                # 管理者は全ナレッジを検索可能
                knowledge_results = db.execute('''
                    SELECT DISTINCT title, content, source_file, keywords
                    FROM external_knowledge
                    WHERE LOWER(title) LIKE ? OR LOWER(content) LIKE ? OR LOWER(keywords) LIKE ?
                    LIMIT 3
                ''', (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')).fetchall()
            else:
                knowledge_results = []
            knowledge.extend([dict(k) for k in knowledge_results])
        
        # 重複を除去（タイトルベース）
        seen_titles = set()
        unique_knowledge = []
        for k in knowledge:
            if k['title'] not in seen_titles:
                seen_titles.add(k['title'])
                unique_knowledge.append(k)
        knowledge = unique_knowledge[:5]
    except Exception as e:
        # external_knowledge テーブルが存在しない場合はスキップ
        knowledge = []
    
    return {
        'videos': unique_videos[:5],
        'transcripts': transcripts[:3],
        'usecases': usecases[:3],
        'knowledge': knowledge
    }

# Rakuten AI 3.0 APIを呼び出す
def call_rakuten_ai(prompt, context="", available_videos=None):
    """Rakuten AI 3.0 APIを呼び出して回答を生成"""
    try:
        # OpenAI互換のエンドポイントを使用
        headers = {
            "Authorization": f"Bearer {RAKUTEN_AI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # 利用可能なビデオリストを作成
        video_list = ""
        if available_videos:
            video_list = "\n利用可能なトレーニング動画:\n" + "\n".join([f"- {v['title']}" for v in available_videos])
        
        messages = [
            {
                "role": "system",
                "content": f"""あなたは業務での生成AI活用を支援するエキスパートアシスタントです。
ユーザーの業種に合わせた具体的で実践的なアドバイスを提供してください。
回答は簡潔で分かりやすく、箇条書きを活用してください。

【重要なルール】
- 回答の中でトレーニングコンテンツや動画を推薦しないでください
- 「〇〇講座」「〇〇マニュアル」「〇〇トレーニング」などの名前を勝手に作成しないでください
- 関連動画の推薦はシステムが自動的に行いますので、あなたは質問への回答のみに集中してください
- 存在しないコンテンツ名を言及しないでください

質問に対する実践的なアドバイスのみを提供してください。"""
            }
        ]
        
        if context:
            messages.append({
                "role": "system",
                "content": f"参考情報:\n{context}"
            })
        
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        payload = {
            "model": RAKUTEN_AI_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        # SSL検証を無効化（社内ネットワーク対応）
        with httpx.Client(verify=False, timeout=60.0) as client:
            response = client.post(
                f"{RAKUTEN_AI_BASE_URL}chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'response': data['choices'][0]['message']['content']
                }
            else:
                return {
                    'success': False,
                    'error': f"API Error: {response.status_code} - {response.text}"
                }
                
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# チャットAPI
@app.route('/api/chat', methods=['POST'])
@login_required
def chat_api():
    data = request.json
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'success': False, 'error': 'メッセージが空です'}), 400
    
    db = get_db()
    industry_id = session.get('industry_id')
    industry_name = session.get('industry_name', '全業種')
    is_admin = session.get('is_admin', False)
    
    # RAG検索で関連コンテンツを取得（業種別アクセス制御適用）
    relevant = search_relevant_content(db, message, industry_id, is_admin)
    
    # コンテキストを構築
    context_parts = []
    
    # 外部ナレッジを優先的に追加（業界の専門知識）
    if relevant.get('knowledge'):
        context_parts.append("【業界の専門知識・ユースケース情報】")
        for k in relevant['knowledge']:
            # コンテンツを適切な長さに切り詰め
            content_preview = k['content'][:500] + '...' if len(k['content']) > 500 else k['content']
            context_parts.append(f"\n■ {k['title']}\n{content_preview}")
    
    if relevant['usecases']:
        context_parts.append("\n【関連ユースケース】")
        for uc in relevant['usecases']:
            context_parts.append(f"- {uc['title']}: {uc['description']}")
    
    if relevant['videos']:
        context_parts.append("\n【関連トレーニング動画】")
        for v in relevant['videos']:
            context_parts.append(f"- {v['title']}: {v.get('description', '')}")
    
    if relevant['transcripts']:
        context_parts.append("\n【動画の内容】")
        for t in relevant['transcripts']:
            content_preview = t['content'][:200] + '...' if len(t['content']) > 200 else t['content']
            context_parts.append(f"- {t['video_title']}: {content_preview}")
    
    context = "\n".join(context_parts) if context_parts else ""
    
    # プロンプトを構築
    prompt = f"業種: {industry_name}\n\n質問: {message}"
    
    # Rakuten AI 3.0 APIを呼び出し（利用可能なビデオ情報を渡す）
    result = call_rakuten_ai(prompt, context, relevant['videos'])
    
    if result['success']:
        # 推薦動画を準備（スラッグを含める）
        recommended_videos = []
        for v in relevant['videos'][:3]:
            # スラッグがなければ生成
            slug = v.get('slug') or ensure_slug_for_video(db, v['id'])
            recommended_videos.append({
                'id': v['id'],
                'slug': slug,
                'title': v['title']
            })
        
        # チャット履歴を保存
        try:
            db.execute('''
                INSERT INTO chat_history (user_id, message, response, recommended_videos)
                VALUES (?, ?, ?, ?)
            ''', (
                session['user_id'],
                message,
                result['response'],
                json.dumps([v['id'] for v in recommended_videos]) if recommended_videos else None
            ))
            db.commit()
        except Exception as e:
            print(f"チャット履歴保存エラー: {e}")
        
        return jsonify({
            'success': True,
            'response': result['response'],
            'recommended_videos': recommended_videos
        })
    else:
        return jsonify({
            'success': False,
            'error': result['error']
        }), 500

# ビデオのトランスクリプトを追加/更新するAPI
@app.route('/api/admin/videos/<int:video_id>/transcript', methods=['POST'])
@admin_required
def update_video_transcript(video_id):
    data = request.json
    content = data.get('content', '').strip()
    content_type = data.get('content_type', 'description')
    
    if not content:
        return jsonify({'error': 'コンテンツが空です'}), 400
    
    db = get_db()
    
    # ビデオの存在確認
    video = db.execute('SELECT id FROM videos WHERE id = ?', (video_id,)).fetchone()
    if not video:
        return jsonify({'error': 'ビデオが見つかりません'}), 404
    
    # 既存のトランスクリプトを削除（同じタイプのもの）
    db.execute('DELETE FROM video_transcripts WHERE video_id = ? AND content_type = ?', (video_id, content_type))
    
    # 新しいトランスクリプトを追加
    db.execute('''
        INSERT INTO video_transcripts (video_id, content, content_type)
        VALUES (?, ?, ?)
    ''', (video_id, content, content_type))
    db.commit()
    
    return jsonify({'success': True, 'message': 'トランスクリプトを保存しました'})

# ========== 自動文字起こし機能 ==========

def transcribe_video_async(video_id, video_path):
    """バックグラウンドで動画を文字起こし"""
    if not WHISPER_AVAILABLE:
        print("[Whisper] Whisper is not available")
        return
    
    # 絶対パスを取得（バックグラウンドスレッドでも正しく動作するように）
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, 'lms.db')
    
    try:
        # ステータスを「処理中」に更新
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        db.execute('UPDATE videos SET transcription_status = ? WHERE id = ?', ('processing', video_id))
        db.commit()
        
        print(f"[Whisper] Starting transcription: {video_path}")
        
        # ffmpegのパスを設定（ローカルにある場合）
        local_ffmpeg = os.path.join(base_dir, 'ffmpeg.exe')
        if os.path.exists(local_ffmpeg):
            os.environ['PATH'] = os.path.dirname(local_ffmpeg) + os.pathsep + os.environ.get('PATH', '')
            print(f"[Whisper] Using local ffmpeg: {local_ffmpeg}")
        
        # Whisperモデルをロード（medium推奨）
        model = whisper.load_model("medium")
        
        # 文字起こし実行
        result = model.transcribe(
            video_path,
            language='ja',
            verbose=False,
            temperature=0,
            condition_on_previous_text=True
        )
        
        transcript_text = result['text']
        print(f"[Whisper] Transcription completed: {len(transcript_text)} characters")
        
        # トランスクリプトをDBに保存
        db.execute('DELETE FROM video_transcripts WHERE video_id = ? AND content_type = ?', 
                   (video_id, 'transcript'))
        db.execute('''
            INSERT INTO video_transcripts (video_id, content, content_type)
            VALUES (?, ?, ?)
        ''', (video_id, transcript_text, 'transcript'))
        
        # 概要を生成（Rakuten AI 3.0を使用）
        summary = generate_video_summary(transcript_text)
        
        # ステータスを「完了」に更新、概要を保存
        db.execute('UPDATE videos SET transcription_status = ?, summary = ? WHERE id = ?', 
                   ('completed', summary, video_id))
        db.commit()
        db.close()
        
        print(f"[Whisper] Processing complete: video_id={video_id}")
        
    except Exception as e:
        print(f"[Whisper] Error: {e}")
        import traceback
        traceback.print_exc()
        # ステータスを「失敗」に更新
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, 'lms.db')
            db = sqlite3.connect(db_path)
            db.execute('UPDATE videos SET transcription_status = ? WHERE id = ?', ('failed', video_id))
            db.commit()
            db.close()
        except:
            pass

def generate_video_summary(transcript_text):
    """トランスクリプトから概要を生成（Rakuten AI 3.0使用）"""
    if not RAKUTEN_AI_API_KEY:
        return None
    
    try:
        # トランスクリプトが長すぎる場合は切り詰め
        max_length = 3000
        if len(transcript_text) > max_length:
            transcript_text = transcript_text[:max_length] + "..."
        
        headers = {
            "Authorization": f"Bearer {RAKUTEN_AI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        messages = [
            {
                "role": "system",
                "content": "あなたは動画コンテンツの概要を作成する専門家です。与えられた文字起こしテキストから、簡潔で分かりやすい概要を日本語で作成してください。概要は3〜5文程度にまとめてください。"
            },
            {
                "role": "user",
                "content": f"以下の動画の文字起こしテキストから概要を作成してください：\n\n{transcript_text}"
            }
        ]
        
        payload = {
            "model": RAKUTEN_AI_MODEL,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        with httpx.Client(verify=False, timeout=60.0) as client:
            response = client.post(
                f"{RAKUTEN_AI_BASE_URL}chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                print(f"概要生成API エラー: {response.status_code}")
                return None
                
    except Exception as e:
        print(f"概要生成エラー: {e}")
        return None

# 文字起こし開始API
@app.route('/api/admin/videos/<int:video_id>/transcribe', methods=['POST'])
@admin_required
def start_transcription(video_id):
    if not WHISPER_AVAILABLE:
        return jsonify({
            'success': False, 
            'error': 'Whisperがインストールされていません。ローカル環境でのみ利用可能です。'
        }), 400
    
    db = get_db()
    video = db.execute('SELECT id, filename, transcription_status FROM videos WHERE id = ?', (video_id,)).fetchone()
    
    if not video:
        return jsonify({'success': False, 'error': 'ビデオが見つかりません'}), 404
    
    if video['transcription_status'] == 'processing':
        return jsonify({'success': False, 'error': '既に処理中です'}), 400
    
    # 動画ファイルのパス（絶対パスを使用）
    base_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(base_dir, app.config['UPLOAD_FOLDER'], video['filename'])
    if not os.path.exists(video_path):
        return jsonify({'success': False, 'error': '動画ファイルが見つかりません'}), 404
    
    # ステータスを「pending」に更新
    db.execute('UPDATE videos SET transcription_status = ? WHERE id = ?', ('pending', video_id))
    db.commit()
    
    # バックグラウンドで文字起こしを開始
    thread = threading.Thread(target=transcribe_video_async, args=(video_id, video_path))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': '文字起こしを開始しました。処理には数分かかる場合があります。'
    })

# 文字起こしステータス確認API
@app.route('/api/admin/videos/<int:video_id>/transcript-status')
@admin_required
def get_transcription_status(video_id):
    db = get_db()
    video = db.execute('SELECT transcription_status, summary FROM videos WHERE id = ?', (video_id,)).fetchone()
    
    if not video:
        return jsonify({'success': False, 'error': 'ビデオが見つかりません'}), 404
    
    return jsonify({
        'success': True,
        'status': video['transcription_status'] or 'none',
        'summary': video['summary']
    })

# ユーザー向け文字起こし取得API
@app.route('/api/videos/<int:video_id>/transcript')
@login_required
def get_video_transcript(video_id):
    db = get_db()
    
    # 動画情報を取得
    video = db.execute('SELECT id, summary, transcription_status FROM videos WHERE id = ?', (video_id,)).fetchone()
    if not video:
        return jsonify({'success': False, 'error': 'ビデオが見つかりません'}), 404
    
    # トランスクリプトを取得
    transcript = db.execute('''
        SELECT content FROM video_transcripts 
        WHERE video_id = ? AND content_type = 'transcript'
        ORDER BY created_at DESC LIMIT 1
    ''', (video_id,)).fetchone()
    
    return jsonify({
        'success': True,
        'summary': video['summary'],
        'transcript': transcript['content'] if transcript else None,
        'status': video['transcription_status'] or 'none'
    })

# ユースケース追加API
@app.route('/api/admin/usecases', methods=['POST'])
@admin_required
def create_usecase():
    data = request.json
    industry_id = data.get('industry_id')
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    keywords = data.get('keywords', '')
    example_prompt = data.get('example_prompt', '')
    
    if not industry_id or not title or not description:
        return jsonify({'error': '業種、タイトル、説明は必須です'}), 400
    
    db = get_db()
    cursor = db.execute('''
        INSERT INTO industry_usecases (industry_id, title, description, keywords, example_prompt)
        VALUES (?, ?, ?, ?, ?)
    ''', (industry_id, title, description, keywords, example_prompt))
    db.commit()
    
    return jsonify({'success': True, 'id': cursor.lastrowid, 'message': 'ユースケースを追加しました'})

# ========== 外部ナレッジ管理API ==========

def create_external_knowledge_table(db):
    """外部ナレッジテーブルを作成"""
    db.execute('''
    CREATE TABLE IF NOT EXISTS external_knowledge (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        industry_id INTEGER,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source_file TEXT,
        section TEXT,
        keywords TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (industry_id) REFERENCES industries (id)
    )
    ''')
    db.commit()

def parse_markdown_sections(content, source_file):
    """Markdownファイルをセクションごとに分割"""
    import re as regex
    sections = []
    current_section = None
    current_content = []
    
    lines = content.split('\n')
    
    for line in lines:
        h2_match = regex.match(r'^## (.+)$', line)
        h3_match = regex.match(r'^### (.+)$', line)
        
        if h2_match or h3_match:
            if current_section and current_content:
                sections.append({
                    'title': current_section,
                    'content': '\n'.join(current_content).strip(),
                    'source_file': source_file
                })
            
            current_section = h2_match.group(1) if h2_match else h3_match.group(1)
            current_section = regex.sub(r'\*\*(.+?)\*\*', r'\1', current_section)
            current_section = current_section.strip()
            current_content = []
        else:
            current_content.append(line)
    
    if current_section and current_content:
        sections.append({
            'title': current_section,
            'content': '\n'.join(current_content).strip(),
            'source_file': source_file
        })
    
    return sections

def extract_knowledge_keywords(content):
    """コンテンツからキーワードを抽出"""
    import re as regex
    bold_keywords = regex.findall(r'\*\*(.+?)\*\*', content)
    
    industry_keywords = [
        '介護', 'ケアプラン', '記録', '文字起こし', '音声', 'AI', '自動化',
        '効率化', '削減', '支援', 'システム', 'モニタリング', '見守り',
        '高齢者', '福祉', 'ケアマネ', '医療', '宿泊', 'ホテル', '旅館',
        '小売', '飲食', 'レストラン', '教育', '研修', 'トレーニング'
    ]
    
    found_keywords = [kw for kw in industry_keywords if kw in content]
    all_keywords = list(set(bold_keywords[:5] + found_keywords[:10]))
    
    return ','.join(all_keywords[:10])

@app.route('/api/admin/knowledge/upload', methods=['POST'])
@admin_required
def upload_knowledge():
    """Markdownファイルをアップロードして外部ナレッジとして登録"""
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルが選択されていません'}), 400
    
    file = request.files['file']
    industry_id = request.form.get('industry_id')
    
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400
    
    if not file.filename.endswith('.md'):
        return jsonify({'error': 'Markdownファイル（.md）のみアップロード可能です'}), 400
    
    if not industry_id:
        return jsonify({'error': '業種を選択してください'}), 400
    
    # company_adminは自業種のナレッジのみアップロード可能
    current_role = session.get('role', 'user')
    user_industry_id = session.get('industry_id')
    if current_role == 'company_admin' and user_industry_id and int(industry_id) != user_industry_id:
        return jsonify({'error': '自業種以外のナレッジはアップロードできません'}), 403
    
    try:
        # ファイル内容を読み込み
        content = file.read().decode('utf-8')
        filename = file.filename
        
        db = get_db()
        
        # テーブルが存在することを確認
        create_external_knowledge_table(db)
        
        # 同じソースファイルの既存ナレッジを削除
        db.execute('DELETE FROM external_knowledge WHERE source_file = ?', (filename,))
        
        # Markdownをセクションに分割
        sections = parse_markdown_sections(content, filename)
        
        inserted = 0
        for section in sections:
            if len(section['content']) < 50:  # 短すぎるセクションはスキップ
                continue
            
            keywords = extract_knowledge_keywords(section['content'])
            
            db.execute('''
                INSERT INTO external_knowledge 
                (industry_id, title, content, source_file, section, keywords)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                industry_id,
                section['title'],
                section['content'],
                section['source_file'],
                section['title'],
                keywords
            ))
            inserted += 1
        
        db.commit()
        
        return jsonify({
            'success': True, 
            'message': f'{inserted}件のナレッジを追加しました',
            'sections': inserted,
            'filename': filename
        })
        
    except Exception as e:
        return jsonify({'error': f'アップロードエラー: {str(e)}'}), 500

@app.route('/api/admin/knowledge/<int:knowledge_id>', methods=['DELETE'])
@admin_required
def delete_knowledge(knowledge_id):
    """ナレッジを削除（company_adminは自業種のみ）"""
    db = get_db()
    current_role = session.get('role', 'user')
    user_industry_id = session.get('industry_id')
    
    # company_adminは自業種のナレッジのみ削除可能
    if current_role == 'company_admin' and user_industry_id:
        knowledge = db.execute('SELECT industry_id FROM external_knowledge WHERE id = ?', (knowledge_id,)).fetchone()
        if knowledge and knowledge['industry_id'] != user_industry_id:
            return jsonify({'error': '他業種のナレッジは削除できません'}), 403
    
    db.execute('DELETE FROM external_knowledge WHERE id = ?', (knowledge_id,))
    db.commit()
    return jsonify({'success': True, 'message': 'ナレッジを削除しました'})

@app.route('/api/admin/knowledge/delete-by-source', methods=['DELETE'])
@admin_required
def delete_knowledge_by_source():
    """ソースファイル単位でナレッジを削除（company_adminは自業種のみ）"""
    data = request.json
    source_file = data.get('source_file')
    
    if not source_file:
        return jsonify({'error': 'ソースファイル名が必要です'}), 400
    
    db = get_db()
    current_role = session.get('role', 'user')
    user_industry_id = session.get('industry_id')
    
    # company_adminは自業種のナレッジのみ削除可能
    if current_role == 'company_admin' and user_industry_id:
        other_industry = db.execute(
            'SELECT id FROM external_knowledge WHERE source_file = ? AND industry_id != ? LIMIT 1',
            (source_file, user_industry_id)
        ).fetchone()
        if other_industry:
            return jsonify({'error': '他業種のナレッジは削除できません'}), 403
    
    db.execute('DELETE FROM external_knowledge WHERE source_file = ?', (source_file,))
    db.commit()
    
    return jsonify({'success': True, 'message': f'{source_file} のナレッジを削除しました'})

@app.route('/api/admin/knowledge')
@admin_required
def get_knowledge_list():
    """ナレッジ一覧を取得（company_adminは自業種のみ）"""
    db = get_db()
    role = session.get('role', 'user')
    user_industry_id = session.get('industry_id')
    
    try:
        if role == 'super_admin':
            knowledge = db.execute('''
                SELECT ek.id, ek.title, ek.source_file, ek.keywords, ek.created_at,
                       i.name as industry_name, i.id as industry_id,
                       substr(ek.content, 1, 100) as preview
                FROM external_knowledge ek
                LEFT JOIN industries i ON ek.industry_id = i.id
                ORDER BY ek.source_file, ek.id
            ''').fetchall()
        elif user_industry_id:
            knowledge = db.execute('''
                SELECT ek.id, ek.title, ek.source_file, ek.keywords, ek.created_at,
                       i.name as industry_name, i.id as industry_id,
                       substr(ek.content, 1, 100) as preview
                FROM external_knowledge ek
                LEFT JOIN industries i ON ek.industry_id = i.id
                WHERE ek.industry_id = ?
                ORDER BY ek.source_file, ek.id
            ''', (user_industry_id,)).fetchall()
        else:
            knowledge = []
        
        return jsonify([dict(k) for k in knowledge])
    except:
        return jsonify([])

@app.route('/api/admin/knowledge/sources')
@admin_required
def get_knowledge_sources():
    """ソースファイル一覧を取得（company_adminは自業種のみ）"""
    db = get_db()
    role = session.get('role', 'user')
    user_industry_id = session.get('industry_id')
    
    try:
        if role == 'super_admin':
            sources = db.execute('''
                SELECT ek.source_file, i.name as industry_name, i.id as industry_id,
                       COUNT(*) as section_count,
                       MIN(ek.created_at) as created_at
                FROM external_knowledge ek
                LEFT JOIN industries i ON ek.industry_id = i.id
                GROUP BY ek.source_file, ek.industry_id
                ORDER BY ek.created_at DESC
            ''').fetchall()
        elif user_industry_id:
            sources = db.execute('''
                SELECT ek.source_file, i.name as industry_name, i.id as industry_id,
                       COUNT(*) as section_count,
                       MIN(ek.created_at) as created_at
                FROM external_knowledge ek
                LEFT JOIN industries i ON ek.industry_id = i.id
                WHERE ek.industry_id = ?
                GROUP BY ek.source_file, ek.industry_id
                ORDER BY ek.created_at DESC
            ''', (user_industry_id,)).fetchall()
        else:
            sources = []
        
        return jsonify([dict(s) for s in sources])
    except:
        return jsonify([])

def migrate_slugs():
    """既存データにスラッグを自動生成（マイグレーション）"""
    if not os.path.exists('lms.db'):
        return
    
    db = get_db()
    
    # カテゴリーのslugカラムが存在するか確認
    try:
        db.execute('SELECT slug FROM categories LIMIT 1')
    except sqlite3.OperationalError:
        # slugカラムが存在しない場合は追加
        print("カテゴリーテーブルにslugカラムを追加しています...")
        db.execute('ALTER TABLE categories ADD COLUMN slug TEXT UNIQUE')
        db.commit()
    
    # 動画のslugカラムが存在するか確認
    try:
        db.execute('SELECT slug FROM videos LIMIT 1')
    except sqlite3.OperationalError:
        # slugカラムが存在しない場合は追加
        print("動画テーブルにslugカラムを追加しています...")
        db.execute('ALTER TABLE videos ADD COLUMN slug TEXT UNIQUE')
        db.commit()
    
    # 既存カテゴリーのスラッグを生成
    categories = db.execute('SELECT id, name, slug FROM categories WHERE slug IS NULL').fetchall()
    if categories:
        print(f"{len(categories)}件のカテゴリーにスラッグを生成しています...")
        existing_slugs = set()
        for cat in categories:
            slug = generate_slug(cat['name'], existing_slugs)
            existing_slugs.add(slug)
            db.execute('UPDATE categories SET slug = ? WHERE id = ?', (slug, cat['id']))
        db.commit()
        print("カテゴリーのスラッグ生成が完了しました")
    
    # 既存動画のスラッグを生成
    videos = db.execute('SELECT id, title, slug FROM videos WHERE slug IS NULL').fetchall()
    if videos:
        print(f"{len(videos)}件の動画にスラッグを生成しています...")
        existing_slugs = set()
        for video in videos:
            slug = generate_slug(video['title'], existing_slugs)
            existing_slugs.add(slug)
            db.execute('UPDATE videos SET slug = ? WHERE id = ?', (slug, video['id']))
        db.commit()
        print("動画のスラッグ生成が完了しました")
    
    db.close()


# ========== 動画Q&A API ==========

@app.route('/api/videos/<int:video_id>/questions', methods=['GET'])
@login_required
def get_video_questions(video_id):
    """動画のQ&A一覧を取得（テナントフィルタ付き）"""
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    
    # 動画の存在確認
    video = db.execute('SELECT id FROM videos WHERE id = ?', (video_id,)).fetchone()
    if not video:
        return jsonify({'error': '動画が見つかりません'}), 404
    
    # テナントフィルタリング
    if role == 'super_admin':
        questions = db.execute('''
            SELECT q.*, u.username, t.name as tenant_name,
                   (SELECT COUNT(*) FROM video_answers WHERE question_id = q.id) as answer_count
            FROM video_questions q
            JOIN users u ON q.user_id = u.id
            LEFT JOIN tenants t ON q.tenant_id = t.id
            WHERE q.video_id = ?
            ORDER BY q.created_at DESC
        ''', (video_id,)).fetchall()
    else:
        questions = db.execute('''
            SELECT q.*, u.username, t.name as tenant_name,
                   (SELECT COUNT(*) FROM video_answers WHERE question_id = q.id) as answer_count
            FROM video_questions q
            JOIN users u ON q.user_id = u.id
            LEFT JOIN tenants t ON q.tenant_id = t.id
            WHERE q.video_id = ? AND q.tenant_id = ?
            ORDER BY q.created_at DESC
        ''', (video_id, tenant_id)).fetchall()
    
    result = []
    for q in questions:
        # 各質問の回答を取得
        answers = db.execute('''
            SELECT a.*, u.username, u.role as user_role
            FROM video_answers a
            JOIN users u ON a.user_id = u.id
            WHERE a.question_id = ?
            ORDER BY a.created_at ASC
        ''', (q['id'],)).fetchall()
        
        result.append({
            'id': q['id'],
            'video_id': q['video_id'],
            'user_id': q['user_id'],
            'username': q['username'],
            'tenant_name': q['tenant_name'] or '',
            'question_text': q['question_text'],
            'answer_count': q['answer_count'],
            'created_at': q['created_at'],
            'answers': [{
                'id': a['id'],
                'user_id': a['user_id'],
                'username': a['username'],
                'answer_text': a['answer_text'],
                'is_admin_answer': bool(a['is_admin_answer']),
                'user_role': a['user_role'],
                'created_at': a['created_at']
            } for a in answers]
        })
    
    return jsonify({'success': True, 'questions': result})


@app.route('/api/videos/<int:video_id>/questions', methods=['POST'])
@login_required
def post_video_question(video_id):
    """動画に質問を投稿"""
    db = get_db()
    data = request.json
    question_text = data.get('question_text', '').strip()
    
    if not question_text:
        return jsonify({'error': '質問内容を入力してください'}), 400
    
    if len(question_text) > 2000:
        return jsonify({'error': '質問は2000文字以内で入力してください'}), 400
    
    # 動画の存在確認
    video = db.execute('SELECT id FROM videos WHERE id = ?', (video_id,)).fetchone()
    if not video:
        return jsonify({'error': '動画が見つかりません'}), 404
    
    user_id = session['user_id']
    tenant_id = session.get('tenant_id')
    
    cursor = db.execute(
        '''INSERT INTO video_questions (video_id, user_id, tenant_id, question_text)
           VALUES (?, ?, ?, ?)''',
        (video_id, user_id, tenant_id, question_text)
    )
    db.commit()
    
    return jsonify({'success': True, 'id': cursor.lastrowid, 'message': '質問を投稿しました'})


@app.route('/api/questions/<int:question_id>/answers', methods=['POST'])
@login_required
def post_question_answer(question_id):
    """質問に回答を投稿"""
    db = get_db()
    data = request.json
    answer_text = data.get('answer_text', '').strip()
    
    if not answer_text:
        return jsonify({'error': '回答内容を入力してください'}), 400
    
    if len(answer_text) > 2000:
        return jsonify({'error': '回答は2000文字以内で入力してください'}), 400
    
    # 質問の存在確認
    question = db.execute('SELECT * FROM video_questions WHERE id = ?', (question_id,)).fetchone()
    if not question:
        return jsonify({'error': '質問が見つかりません'}), 404
    
    # テナント境界チェック（super_admin以外は同テナントの質問のみ）
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    if role != 'super_admin' and question['tenant_id'] != tenant_id:
        return jsonify({'error': 'この質問への回答権限がありません'}), 403
    
    user_id = session['user_id']
    is_admin_answer = 1 if role in ('super_admin', 'company_admin') else 0
    
    cursor = db.execute(
        '''INSERT INTO video_answers (question_id, user_id, answer_text, is_admin_answer)
           VALUES (?, ?, ?, ?)''',
        (question_id, user_id, answer_text, is_admin_answer)
    )
    db.commit()
    
    return jsonify({'success': True, 'id': cursor.lastrowid, 'message': '回答を投稿しました'})


@app.route('/api/questions/<int:question_id>', methods=['PUT'])
@login_required
def update_question(question_id):
    """質問を編集（投稿者本人のみ）"""
    db = get_db()
    question = db.execute('SELECT * FROM video_questions WHERE id = ?', (question_id,)).fetchone()
    if not question:
        return jsonify({'error': '質問が見つかりません'}), 404
    
    # 投稿者本人のみ編集可能
    user_id = session['user_id']
    if question['user_id'] != user_id:
        return jsonify({'error': 'この質問を編集する権限がありません'}), 403
    
    data = request.json
    question_text = data.get('question_text', '').strip()
    
    if not question_text:
        return jsonify({'error': '質問内容を入力してください'}), 400
    
    if len(question_text) > 2000:
        return jsonify({'error': '質問は2000文字以内で入力してください'}), 400
    
    db.execute(
        '''UPDATE video_questions SET question_text = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?''',
        (question_text, question_id)
    )
    db.commit()
    
    return jsonify({'success': True, 'message': '質問を更新しました'})


@app.route('/api/questions/<int:question_id>', methods=['DELETE'])
@login_required
def delete_question(question_id):
    """質問を削除"""
    db = get_db()
    question = db.execute('SELECT * FROM video_questions WHERE id = ?', (question_id,)).fetchone()
    if not question:
        return jsonify({'error': '質問が見つかりません'}), 404
    
    role = session.get('role', 'user')
    user_id = session['user_id']
    tenant_id = session.get('tenant_id')
    
    # 権限チェック
    if role == 'super_admin':
        pass  # 全削除可能
    elif role == 'company_admin' and question['tenant_id'] == tenant_id:
        pass  # 自テナント内の質問は削除可能
    elif question['user_id'] == user_id:
        pass  # 自分の質問は削除可能
    else:
        return jsonify({'error': 'この質問を削除する権限がありません'}), 403
    
    # 質問に紐づく回答も削除（CASCADE）
    db.execute('DELETE FROM video_answers WHERE question_id = ?', (question_id,))
    db.execute('DELETE FROM video_questions WHERE id = ?', (question_id,))
    db.commit()
    
    return jsonify({'success': True, 'message': '質問を削除しました'})


@app.route('/api/answers/<int:answer_id>', methods=['PUT'])
@login_required
def update_answer(answer_id):
    """回答を編集（投稿者本人のみ）"""
    db = get_db()
    answer = db.execute('''
        SELECT a.*, q.tenant_id 
        FROM video_answers a 
        JOIN video_questions q ON a.question_id = q.id 
        WHERE a.id = ?
    ''', (answer_id,)).fetchone()
    if not answer:
        return jsonify({'error': '回答が見つかりません'}), 404
    
    # 投稿者本人のみ編集可能
    user_id = session['user_id']
    if answer['user_id'] != user_id:
        return jsonify({'error': 'この回答を編集する権限がありません'}), 403
    
    data = request.json
    answer_text = data.get('answer_text', '').strip()
    
    if not answer_text:
        return jsonify({'error': '回答内容を入力してください'}), 400
    
    if len(answer_text) > 2000:
        return jsonify({'error': '回答は2000文字以内で入力してください'}), 400
    
    db.execute(
        '''UPDATE video_answers SET answer_text = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?''',
        (answer_text, answer_id)
    )
    db.commit()
    
    return jsonify({'success': True, 'message': '回答を更新しました'})


@app.route('/api/answers/<int:answer_id>', methods=['DELETE'])
@login_required
def delete_answer(answer_id):
    """回答を削除"""
    db = get_db()
    answer = db.execute('''
        SELECT a.*, q.tenant_id 
        FROM video_answers a 
        JOIN video_questions q ON a.question_id = q.id 
        WHERE a.id = ?
    ''', (answer_id,)).fetchone()
    if not answer:
        return jsonify({'error': '回答が見つかりません'}), 404
    
    role = session.get('role', 'user')
    user_id = session['user_id']
    tenant_id = session.get('tenant_id')
    
    # 権限チェック
    if role == 'super_admin':
        pass  # 全削除可能
    elif role == 'company_admin' and answer['tenant_id'] == tenant_id:
        pass  # 自テナント内の回答は削除可能
    elif answer['user_id'] == user_id:
        pass  # 自分の回答は削除可能
    else:
        return jsonify({'error': 'この回答を削除する権限がありません'}), 403
    
    db.execute('DELETE FROM video_answers WHERE id = ?', (answer_id,))
    db.commit()
    
    return jsonify({'success': True, 'message': '回答を削除しました'})


# ========== Q&A分析ダッシュボード ==========

@app.route('/admin/qa-analytics')
@admin_required
def qa_analytics_dashboard():
    return render_template('qa_analytics.html')


@app.route('/api/admin/qa-analytics/summary')
@admin_required
def qa_analytics_summary():
    """Q&A分析の集計データ"""
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    
    # テナントフィルタリング
    q_tenant_filter = ""
    q_params = []
    if role != 'super_admin' and tenant_id:
        q_tenant_filter = "AND q.tenant_id = ?"
        q_params = [tenant_id]
    
    # --- 1) 総合統計 ---
    total_questions = db.execute(f'''
        SELECT COUNT(*) as cnt FROM video_questions q WHERE 1=1 {q_tenant_filter}
    ''', q_params).fetchone()['cnt']
    
    total_answers = db.execute(f'''
        SELECT COUNT(*) as cnt FROM video_answers a
        JOIN video_questions q ON a.question_id = q.id
        WHERE 1=1 {q_tenant_filter}
    ''', q_params).fetchone()['cnt']
    
    unanswered = db.execute(f'''
        SELECT COUNT(*) as cnt FROM video_questions q
        WHERE (SELECT COUNT(*) FROM video_answers WHERE question_id = q.id) = 0
        {q_tenant_filter}
    ''', q_params).fetchone()['cnt']
    
    answer_rate = round((1 - unanswered / total_questions) * 100, 1) if total_questions > 0 else 0
    
    # --- 2) 動画別Q&Aランキング ---
    video_ranking = db.execute(f'''
        SELECT v.id, v.title, v.slug,
               COUNT(DISTINCT q.id) as question_count,
               (SELECT COUNT(*) FROM video_answers a2 
                JOIN video_questions q2 ON a2.question_id = q2.id 
                WHERE q2.video_id = v.id {'AND q2.tenant_id = ?' if q_tenant_filter else ''}) as answer_count,
               (SELECT COUNT(*) FROM video_questions q3 
                WHERE q3.video_id = v.id {'AND q3.tenant_id = ?' if q_tenant_filter else ''}
                AND (SELECT COUNT(*) FROM video_answers WHERE question_id = q3.id) = 0) as unanswered_count
        FROM videos v
        JOIN video_questions q ON q.video_id = v.id
        WHERE 1=1 {q_tenant_filter}
        GROUP BY v.id, v.title, v.slug
        ORDER BY question_count DESC
        LIMIT 20
    ''', q_params * 3 if q_tenant_filter else []).fetchall()
    
    # --- 3) 未回答の質問一覧 ---
    unanswered_questions = db.execute(f'''
        SELECT q.id, q.question_text, q.created_at, 
               u.username, t.name as tenant_name,
               v.title as video_title, v.slug as video_slug
        FROM video_questions q
        JOIN users u ON q.user_id = u.id
        LEFT JOIN tenants t ON q.tenant_id = t.id
        JOIN videos v ON q.video_id = v.id
        WHERE (SELECT COUNT(*) FROM video_answers WHERE question_id = q.id) = 0
        {q_tenant_filter}
        ORDER BY q.created_at DESC
        LIMIT 50
    ''', q_params).fetchall()
    
    # --- 4) ユーザー別Q&A統計 ---
    user_stats = db.execute(f'''
        SELECT u.id, u.username, u.company_name,
               (SELECT COUNT(*) FROM video_questions q2 WHERE q2.user_id = u.id {'AND q2.tenant_id = ?' if q_tenant_filter else ''}) as question_count,
               (SELECT COUNT(*) FROM video_answers a2 
                JOIN video_questions q3 ON a2.question_id = q3.id
                WHERE a2.user_id = u.id {'AND q3.tenant_id = ?' if q_tenant_filter else ''}) as answer_count
        FROM users u
        WHERE (
            EXISTS (SELECT 1 FROM video_questions q4 WHERE q4.user_id = u.id {'AND q4.tenant_id = ?' if q_tenant_filter else ''})
            OR EXISTS (SELECT 1 FROM video_answers a3 JOIN video_questions q5 ON a3.question_id = q5.id WHERE a3.user_id = u.id {'AND q5.tenant_id = ?' if q_tenant_filter else ''})
        )
        ORDER BY question_count + answer_count DESC
        LIMIT 20
    ''', q_params * 4 if q_tenant_filter else []).fetchall()
    
    # --- 5) 日別Q&Aアクティビティ（過去30日） ---
    days = request.args.get('days', 30, type=int)
    daily_activity = db.execute(f'''
        SELECT date, SUM(questions) as questions, SUM(answers) as answers FROM (
            SELECT DATE(q.created_at) as date, COUNT(*) as questions, 0 as answers
            FROM video_questions q
            WHERE q.created_at >= datetime('now', '-' || ? || ' days') {q_tenant_filter}
            GROUP BY DATE(q.created_at)
            UNION ALL
            SELECT DATE(a.created_at) as date, 0 as questions, COUNT(*) as answers
            FROM video_answers a
            JOIN video_questions q ON a.question_id = q.id
            WHERE a.created_at >= datetime('now', '-' || ? || ' days') {q_tenant_filter}
            GROUP BY DATE(a.created_at)
        ) combined
        GROUP BY date
        ORDER BY date
    ''', [days] + q_params + [days] + q_params).fetchall()
    
    # --- 6) テナント別統計（super_adminのみ） ---
    tenant_stats = []
    if role == 'super_admin':
        tenant_stats = db.execute('''
            SELECT t.id, t.name,
                   COUNT(DISTINCT q.id) as question_count,
                   (SELECT COUNT(*) FROM video_answers a2 
                    JOIN video_questions q2 ON a2.question_id = q2.id 
                    WHERE q2.tenant_id = t.id) as answer_count
            FROM tenants t
            LEFT JOIN video_questions q ON q.tenant_id = t.id
            GROUP BY t.id, t.name
            HAVING question_count > 0
            ORDER BY question_count DESC
        ''').fetchall()
    
    return jsonify({
        'summary': {
            'total_questions': total_questions,
            'total_answers': total_answers,
            'unanswered': unanswered,
            'answer_rate': answer_rate
        },
        'video_ranking': [dict(v) for v in video_ranking],
        'unanswered_questions': [dict(q) for q in unanswered_questions],
        'user_stats': [dict(u) for u in user_stats],
        'daily_activity': [dict(d) for d in daily_activity],
        'tenant_stats': [dict(t) for t in tenant_stats]
    })


# ========== マイQ&A（一般ユーザー向け） ==========

@app.route('/api/my-questions')
@login_required
def get_my_questions():
    """自分が投稿した質問一覧 + 同テナントのQ&Aを取得"""
    db = get_db()
    user_id = session['user_id']
    tenant_id = session.get('tenant_id')
    
    questions = db.execute('''
        SELECT q.id, q.question_text, q.created_at, q.updated_at,
               v.title as video_title, v.slug as video_slug,
               (SELECT COUNT(*) FROM video_answers WHERE question_id = q.id) as answer_count
        FROM video_questions q
        JOIN videos v ON q.video_id = v.id
        WHERE q.user_id = ?
        ORDER BY q.created_at DESC
    ''', (user_id,)).fetchall()
    
    # 自分が投稿した回答一覧も取得
    answers = db.execute('''
        SELECT a.id, a.answer_text, a.created_at, a.updated_at,
               q.question_text, q.id as question_id,
               v.title as video_title, v.slug as video_slug,
               qu.username as question_author
        FROM video_answers a
        JOIN video_questions q ON a.question_id = q.id
        JOIN videos v ON q.video_id = v.id
        JOIN users qu ON q.user_id = qu.id
        WHERE a.user_id = ?
        ORDER BY a.created_at DESC
    ''', (user_id,)).fetchall()
    
    # 同テナント（同じ会社）のQ&Aを取得（自分の投稿は除外）
    tenant_qa = []
    if tenant_id:
        tenant_questions = db.execute('''
            SELECT q.id, q.question_text, q.created_at, q.updated_at,
                   v.title as video_title, v.slug as video_slug,
                   u.username as author,
                   (SELECT COUNT(*) FROM video_answers WHERE question_id = q.id) as answer_count
            FROM video_questions q
            JOIN videos v ON q.video_id = v.id
            JOIN users u ON q.user_id = u.id
            WHERE q.tenant_id = ?
              AND q.user_id != ?
            ORDER BY q.created_at DESC
            LIMIT 50
        ''', (tenant_id, user_id)).fetchall()
        
        for q in tenant_questions:
            qd = dict(q)
            # 各質問の回答を個別に取得
            ans = db.execute('''
                SELECT a.answer_text, u.username as author,
                       a.is_admin_answer, a.created_at
                FROM video_answers a
                JOIN users u ON a.user_id = u.id
                WHERE a.question_id = ?
                ORDER BY a.created_at ASC
            ''', (qd['id'],)).fetchall()
            qd['answers'] = [dict(a) for a in ans]
            tenant_qa.append(qd)
    
    return jsonify({
        'success': True,
        'my_questions': [dict(q) for q in questions],
        'my_answers': [dict(a) for a in answers],
        'tenant_questions': tenant_qa
    })


# ========== お知らせ・通知 API ==========

@app.route('/api/announcements', methods=['GET'])
@login_required
def get_announcements():
    """有効な通知一覧を取得（ユーザー向け）"""
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if role == 'super_admin':
        # super_adminは全通知を閲覧
        announcements = db.execute('''
            SELECT a.*, u.username as author_name, t.name as tenant_name
            FROM announcements a
            JOIN users u ON a.author_id = u.id
            LEFT JOIN tenants t ON a.target_tenant_id = t.id
            WHERE a.is_active = 1
              AND a.publish_at <= ?
              AND (a.expires_at IS NULL OR a.expires_at > ?)
            ORDER BY a.created_at DESC
        ''', (now, now)).fetchall()
    else:
        # 一般ユーザー/company_admin: 全体通知 + 自テナント通知
        announcements = db.execute('''
            SELECT a.*, u.username as author_name, t.name as tenant_name
            FROM announcements a
            JOIN users u ON a.author_id = u.id
            LEFT JOIN tenants t ON a.target_tenant_id = t.id
            WHERE a.is_active = 1
              AND a.publish_at <= ?
              AND (a.expires_at IS NULL OR a.expires_at > ?)
              AND (a.target_tenant_id IS NULL OR a.target_tenant_id = ?)
            ORDER BY a.created_at DESC
        ''', (now, now, tenant_id)).fetchall()
    
    result = [{
        'id': a['id'],
        'title': a['title'],
        'content': a['content'],
        'type': a['type'],
        'author_name': a['author_name'],
        'tenant_name': a['tenant_name'],
        'target_tenant_id': a['target_tenant_id'],
        'is_active': bool(a['is_active']),
        'publish_at': a['publish_at'],
        'expires_at': a['expires_at'],
        'created_at': a['created_at']
    } for a in announcements]
    
    return jsonify({'success': True, 'announcements': result})


@app.route('/api/admin/announcements', methods=['GET'])
@admin_required
def get_admin_announcements():
    """管理者向け通知一覧（全通知、有効/無効含む）"""
    db = get_db()
    role = session.get('role', 'user')
    tenant_id = session.get('tenant_id')
    
    if role == 'super_admin':
        announcements = db.execute('''
            SELECT a.*, u.username as author_name, t.name as tenant_name
            FROM announcements a
            JOIN users u ON a.author_id = u.id
            LEFT JOIN tenants t ON a.target_tenant_id = t.id
            ORDER BY a.created_at DESC
        ''').fetchall()
    else:
        # company_admin: 全体通知 + 自テナント通知のみ
        announcements = db.execute('''
            SELECT a.*, u.username as author_name, t.name as tenant_name
            FROM announcements a
            JOIN users u ON a.author_id = u.id
            LEFT JOIN tenants t ON a.target_tenant_id = t.id
            WHERE a.target_tenant_id IS NULL OR a.target_tenant_id = ?
            ORDER BY a.created_at DESC
        ''', (tenant_id,)).fetchall()
    
    result = [{
        'id': a['id'],
        'title': a['title'],
        'content': a['content'],
        'type': a['type'],
        'author_name': a['author_name'],
        'author_id': a['author_id'],
        'tenant_name': a['tenant_name'],
        'target_tenant_id': a['target_tenant_id'],
        'is_active': bool(a['is_active']),
        'publish_at': a['publish_at'],
        'expires_at': a['expires_at'],
        'created_at': a['created_at']
    } for a in announcements]
    
    return jsonify({'success': True, 'announcements': result})


@app.route('/api/admin/announcements', methods=['POST'])
@admin_required
def create_announcement():
    """通知を作成"""
    data = request.json
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    ann_type = data.get('type', 'info').strip()
    target_tenant_id = data.get('target_tenant_id')
    publish_at = data.get('publish_at')
    expires_at = data.get('expires_at')
    
    if not title or not content:
        return jsonify({'error': 'タイトルと内容は必須です'}), 400
    
    if ann_type not in ('info', 'warning', 'success'):
        return jsonify({'error': '無効な通知タイプです。info/warning/success から選択してください'}), 400
    
    role = session.get('role', 'user')
    current_tenant_id = session.get('tenant_id')
    
    # company_adminの権限制限
    if role == 'company_admin':
        if target_tenant_id is None or str(target_tenant_id) == '':
            # 全体通知は不可
            return jsonify({'error': '全体通知はsuper_adminのみ作成できます'}), 403
        # 自テナントに強制設定
        target_tenant_id = current_tenant_id
    
    # target_tenant_idの処理
    if target_tenant_id == '' or target_tenant_id == 'all':
        target_tenant_id = None
    
    if not publish_at:
        publish_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if expires_at == '':
        expires_at = None
    
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO announcements (author_id, title, content, type, target_tenant_id, publish_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (session['user_id'], title, content, ann_type, target_tenant_id, publish_at, expires_at)
    )
    db.commit()
    
    return jsonify({'success': True, 'id': cursor.lastrowid, 'message': 'お知らせを作成しました'})


@app.route('/api/admin/announcements/<int:ann_id>', methods=['PUT'])
@admin_required
def update_announcement(ann_id):
    """通知を編集"""
    db = get_db()
    announcement = db.execute('SELECT * FROM announcements WHERE id = ?', (ann_id,)).fetchone()
    if not announcement:
        return jsonify({'error': 'お知らせが見つかりません'}), 404
    
    role = session.get('role', 'user')
    current_tenant_id = session.get('tenant_id')
    
    # company_adminは自テナント通知のみ編集可
    if role == 'company_admin' and announcement['target_tenant_id'] != current_tenant_id:
        return jsonify({'error': 'このお知らせを編集する権限がありません'}), 403
    
    data = request.json
    title = data.get('title', announcement['title']).strip()
    content = data.get('content', announcement['content']).strip()
    ann_type = data.get('type', announcement['type']).strip()
    is_active = data.get('is_active', announcement['is_active'])
    publish_at = data.get('publish_at', announcement['publish_at'])
    expires_at = data.get('expires_at', announcement['expires_at'])
    
    if not title or not content:
        return jsonify({'error': 'タイトルと内容は必須です'}), 400
    
    if expires_at == '':
        expires_at = None
    
    db.execute(
        '''UPDATE announcements 
           SET title = ?, content = ?, type = ?, is_active = ?, publish_at = ?, expires_at = ?
           WHERE id = ?''',
        (title, content, ann_type, 1 if is_active else 0, publish_at, expires_at, ann_id)
    )
    db.commit()
    
    return jsonify({'success': True, 'message': 'お知らせを更新しました'})


@app.route('/api/admin/announcements/<int:ann_id>', methods=['DELETE'])
@admin_required
def delete_announcement(ann_id):
    """通知を削除"""
    db = get_db()
    announcement = db.execute('SELECT * FROM announcements WHERE id = ?', (ann_id,)).fetchone()
    if not announcement:
        return jsonify({'error': 'お知らせが見つかりません'}), 404
    
    role = session.get('role', 'user')
    current_tenant_id = session.get('tenant_id')
    
    # company_adminは自テナント通知のみ削除可
    if role == 'company_admin' and announcement['target_tenant_id'] != current_tenant_id:
        return jsonify({'error': 'このお知らせを削除する権限がありません'}), 403
    
    db.execute('DELETE FROM announcements WHERE id = ?', (ann_id,))
    db.commit()
    
    return jsonify({'success': True, 'message': 'お知らせを削除しました'})


if __name__ == '__main__':
    # videosフォルダを作成
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # データベースの差分マイグレーションを自動実行
    # （DBが存在しない場合は新規作成、存在する場合は差分のみ適用）
    try:
        from migrate_db import run_migrations
        run_migrations(verbose=True)
    except ImportError:
        # migrate_db.py がない環境（PythonAnywhereなど）ではフォールバック
        if not os.path.exists('lms.db'):
            print("データベースが存在しません。init_db.py を実行してください。")
        else:
            migrate_slugs()
            migrate_transcription_columns()
            migrate_tenant_role_columns()
    
    # ポート番号を環境変数から取得（デプロイ環境対応）
    port = int(os.environ.get('PORT', 5000))
    
    # 本番環境ではdebug=Falseにする
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    app.run(debug=debug, host='0.0.0.0', port=port)
