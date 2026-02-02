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
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}

# ========== Rakuten AI 3.0 API設定 ==========
# APIキーは環境変数または.envファイルから読み込み（ハードコード禁止）
RAKUTEN_AI_API_KEY = os.environ.get('RAKUTEN_AI_API_KEY', '')
RAKUTEN_AI_BASE_URL = os.environ.get('RAKUTEN_AI_BASE_URL', 'https://api.ai.public.rakuten-it.com/rakutenllms/v1/')
RAKUTEN_AI_MODEL = os.environ.get('RAKUTEN_AI_MODEL', 'rakutenai-3.0')

# データベース接続
def get_db():
    db = sqlite3.connect('lms.db')
    db.row_factory = sqlite3.Row
    return db

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

# 管理者権限デコレータ
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        db = get_db()
        user = db.execute('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if not user or not user['is_admin']:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

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
            
            # 業種名を取得
            if user['industry_id']:
                industry = db.execute('SELECT name FROM industries WHERE id = ?', (user['industry_id'],)).fetchone()
                session['industry_name'] = industry['name'] if industry else None
            else:
                session['industry_name'] = None
            
            return jsonify({'success': True, 'is_admin': user['is_admin']})
        
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
    videos = db.execute('''
        SELECT v.*, c.name as category_name, c.color as category_color
        FROM videos v
        LEFT JOIN categories c ON v.category_id = c.id
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
    videos = db.execute('''
        SELECT v.*, c.name as category_name 
        FROM videos v 
        LEFT JOIN categories c ON v.category_id = c.id 
        ORDER BY v.created_at DESC
    ''').fetchall()
    users = db.execute('''
        SELECT u.id, u.username, u.email, u.company_name, u.created_at, i.name as industry_name
        FROM users u
        LEFT JOIN industries i ON u.industry_id = i.id
        ORDER BY u.created_at DESC
    ''').fetchall()
    categories = db.execute('SELECT * FROM categories ORDER BY display_order, created_at').fetchall()
    industries = db.execute('SELECT * FROM industries ORDER BY id').fetchall()
    
    # 各カテゴリーのアクセス制御情報を取得
    category_access = {}
    for cat in categories:
        access = db.execute('''
            SELECT i.id, i.name FROM industries i
            JOIN category_industry_access cia ON i.id = cia.industry_id
            WHERE cia.category_id = ?
        ''', (cat['id'],)).fetchall()
        category_access[cat['id']] = [dict(a) for a in access]
    
    return render_template('admin.html', videos=videos, users=users, categories=categories, 
                           industries=industries, category_access=category_access)

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
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    industry_id = data.get('industry_id')
    company_name = data.get('company_name', '')
    is_admin = data.get('is_admin', False)
    
    if not username or not email or not password:
        return jsonify({'error': 'ユーザー名、メール、パスワードは必須です'}), 400
    
    db = get_db()
    
    # ユーザー名の重複チェック
    existing = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if existing:
        return jsonify({'error': 'このユーザー名は既に使用されています'}), 400
    
    # メールの重複チェック
    existing_email = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    if existing_email:
        return jsonify({'error': 'このメールアドレスは既に使用されています'}), 400
    
    try:
        cursor = db.execute(
            '''INSERT INTO users (username, email, password_hash, industry_id, company_name, is_admin)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (username, email, generate_password_hash(password), 
             industry_id if industry_id else None, company_name, 1 if is_admin else 0)
        )
        db.commit()
        return jsonify({'success': True, 'id': cursor.lastrowid, 'message': 'ユーザーを作成しました'})
    except sqlite3.IntegrityError as e:
        return jsonify({'error': f'ユーザーの作成に失敗しました: {str(e)}'}), 400

# ユーザー更新
@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')  # 空の場合は更新しない
    industry_id = data.get('industry_id')
    company_name = data.get('company_name', '')
    is_admin = data.get('is_admin', False)
    
    if not username or not email:
        return jsonify({'error': 'ユーザー名とメールは必須です'}), 400
    
    db = get_db()
    
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
            # パスワードも更新
            db.execute(
                '''UPDATE users SET username = ?, email = ?, password_hash = ?, 
                   industry_id = ?, company_name = ?, is_admin = ? WHERE id = ?''',
                (username, email, generate_password_hash(password),
                 industry_id if industry_id else None, company_name, 1 if is_admin else 0, user_id)
            )
        else:
            # パスワードは更新しない
            db.execute(
                '''UPDATE users SET username = ?, email = ?, 
                   industry_id = ?, company_name = ?, is_admin = ? WHERE id = ?''',
                (username, email, industry_id if industry_id else None, company_name, 
                 1 if is_admin else 0, user_id)
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
    user = db.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        return jsonify({'error': 'ユーザーが見つかりません'}), 404
    
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
        SELECT id, username, email, industry_id, company_name, is_admin
        FROM users WHERE id = ?
    ''', (user_id,)).fetchone()
    
    if not user:
        return jsonify({'error': 'ユーザーが見つかりません'}), 404
    
    return jsonify(dict(user))

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
def search_relevant_content(db, question, industry_id):
    """質問に関連するコンテンツを検索"""
    keywords = question.lower().split()
    
    # ビデオを検索（タイトルと説明文）
    videos = []
    for keyword in keywords[:5]:  # 最初の5キーワードで検索
        search_results = db.execute('''
            SELECT DISTINCT v.id, v.title, v.description, c.name as category_name
            FROM videos v
            LEFT JOIN categories c ON v.category_id = c.id
            WHERE LOWER(v.title) LIKE ? OR LOWER(v.description) LIKE ?
            LIMIT 5
        ''', (f'%{keyword}%', f'%{keyword}%')).fetchall()
        videos.extend([dict(v) for v in search_results])
    
    # 重複を除去
    seen_ids = set()
    unique_videos = []
    for v in videos:
        if v['id'] not in seen_ids:
            seen_ids.add(v['id'])
            unique_videos.append(v)
    
    # トランスクリプトを検索
    transcripts = []
    for keyword in keywords[:3]:
        transcript_results = db.execute('''
            SELECT vt.content, v.id as video_id, v.title as video_title
            FROM video_transcripts vt
            JOIN videos v ON vt.video_id = v.id
            WHERE LOWER(vt.content) LIKE ?
            LIMIT 3
        ''', (f'%{keyword}%',)).fetchall()
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
    
    return {
        'videos': unique_videos[:5],
        'transcripts': transcripts[:3],
        'usecases': usecases[:3]
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
    
    # RAG検索で関連コンテンツを取得
    relevant = search_relevant_content(db, message, industry_id)
    
    # コンテキストを構築
    context_parts = []
    
    if relevant['usecases']:
        context_parts.append("【関連ユースケース】")
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

if __name__ == '__main__':
    # videosフォルダを作成
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # データベースが存在しない場合は初期化
    if not os.path.exists('lms.db'):
        print("データベースが存在しません。init_db.py を実行してください。")
    else:
        # 既存データにスラッグを自動生成
        migrate_slugs()
    
    # ポート番号を環境変数から取得（デプロイ環境対応）
    port = int(os.environ.get('PORT', 5000))
    
    # 本番環境ではdebug=Falseにする
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    app.run(debug=debug, host='0.0.0.0', port=port)
