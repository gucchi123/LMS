import sqlite3
from werkzeug.security import generate_password_hash
import os
import shutil
import sys

# Windows環境での日本語出力対応
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def init_database():
    """データベースを初期化し、サンプルデータを作成"""
    
    # 既存のデータベースがあれば削除
    if os.path.exists('lms.db'):
        os.remove('lms.db')
        print("既存のデータベースを削除しました")
    
    # データベース接続
    conn = sqlite3.connect('lms.db')
    cursor = conn.cursor()
    
    # Usersテーブル作成
    cursor.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Videosテーブル作成
    cursor.execute('''
    CREATE TABLE videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        filename TEXT NOT NULL,
        uploaded_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (uploaded_by) REFERENCES users (id)
    )
    ''')
    
    # Progressテーブル作成（視聴進捗管理）
    cursor.execute('''
    CREATE TABLE progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        video_id INTEGER NOT NULL,
        progress_percent REAL DEFAULT 0,
        last_position REAL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (video_id) REFERENCES videos (id),
        UNIQUE(user_id, video_id)
    )
    ''')
    
    # デフォルトユーザーを作成
    # 管理者アカウント: admin / admin123
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, is_admin)
    VALUES (?, ?, ?, ?)
    ''', ('admin', 'admin@example.com', generate_password_hash('admin123'), 1))
    
    # 一般ユーザー: user1 / user123
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, is_admin)
    VALUES (?, ?, ?, ?)
    ''', ('user1', 'user1@example.com', generate_password_hash('user123'), 0))
    
    # 一般ユーザー: user2 / user123
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, is_admin)
    VALUES (?, ?, ?, ?)
    ''', ('user2', 'user2@example.com', generate_password_hash('user123'), 0))
    
    # videosフォルダを作成
    os.makedirs('videos', exist_ok=True)
    
    # サンプル動画をコピー
    sample_video = 'Rakuten AI for Businessのご紹介_1111_20260114_204516.mp4'
    if os.path.exists(sample_video):
        destination = os.path.join('videos', sample_video)
        if not os.path.exists(destination):
            shutil.copy(sample_video, destination)
            print(f"サンプル動画をコピーしました: {sample_video}")
        
        # サンプル動画をデータベースに登録
        cursor.execute('''
        INSERT INTO videos (title, description, filename, uploaded_by)
        VALUES (?, ?, ?, ?)
        ''', (
            'Rakuten AI for Businessのご紹介',
            'Rakuten AI for Businessの機能と特徴を紹介する動画です。',
            sample_video,
            1  # admin user
        ))
    
    conn.commit()
    conn.close()
    
    print("\n=== データベースの初期化が完了しました ===")
    print("\nデフォルトアカウント:")
    print("  管理者:")
    print("    ユーザー名: admin")
    print("    パスワード: admin123")
    print("\n  一般ユーザー1:")
    print("    ユーザー名: user1")
    print("    パスワード: user123")
    print("\n  一般ユーザー2:")
    print("    ユーザー名: user2")
    print("    パスワード: user123")
    print("\n==========================================\n")

if __name__ == '__main__':
    init_database()
