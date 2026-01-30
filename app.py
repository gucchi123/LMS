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

# ルート - ログインページへリダイレクト
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
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
            return jsonify({'success': True, 'is_admin': user['is_admin']})
        
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    
    return render_template('login.html')

# ログアウト
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ダッシュボード（動画一覧）
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    videos = db.execute('SELECT * FROM videos ORDER BY created_at DESC').fetchall()
    
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
    videos = db.execute('SELECT * FROM videos ORDER BY created_at DESC').fetchall()
    users = db.execute('SELECT id, username, email, created_at FROM users ORDER BY created_at DESC').fetchall()
    
    return render_template('admin.html', videos=videos, users=users)

# 動画アップロードAPI
@app.route('/api/admin/upload', methods=['POST'])
@admin_required
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file'}), 400
    
    file = request.files['video']
    title = request.form.get('title')
    description = request.form.get('description', '')
    
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
            'INSERT INTO videos (title, description, filename, uploaded_by) VALUES (?, ?, ?, ?)',
            (title, description, filename, session['user_id'])
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
