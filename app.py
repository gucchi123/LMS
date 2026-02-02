from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
app.config['UPLOAD_FOLDER'] = 'videos'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}

# データベース接続
def get_db():
    db = sqlite3.connect('lms.db')
    db.row_factory = sqlite3.Row
    return db

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
@app.route('/courses/<int:category_id>')
@login_required
def category_detail(category_id):
    db = get_db()
    industry_id = session.get('industry_id')
    is_admin = session.get('is_admin')
    
    # カテゴリー情報を取得
    category = db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
    
    if not category:
        return "Category not found", 404
    
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
@app.route('/watch/<int:video_id>')
@login_required
def watch_video(video_id):
    db = get_db()
    video = db.execute('SELECT * FROM videos WHERE id = ?', (video_id,)).fetchone()
    
    if not video:
        return "Video not found", 404
    
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
        db.execute(
            'INSERT INTO videos (title, description, filename, category_id, uploaded_by) VALUES (?, ?, ?, ?, ?)',
            (title, description, filename, category_id if category_id else None, session['user_id'])
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
    cursor = db.execute(
        '''INSERT INTO categories (name, description, icon, color, parent_id, display_order)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (name, description, icon, color, parent_id if parent_id else None, display_order)
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

if __name__ == '__main__':
    # videosフォルダを作成
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # データベースが存在しない場合は初期化
    if not os.path.exists('lms.db'):
        print("データベースが存在しません。init_db.py を実行してください。")
    
    # ポート番号を環境変数から取得（デプロイ環境対応）
    port = int(os.environ.get('PORT', 5000))
    
    # 本番環境ではdebug=Falseにする
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    app.run(debug=debug, host='0.0.0.0', port=port)
