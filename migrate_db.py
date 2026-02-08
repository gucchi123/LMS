"""
LMS データベース差分マイグレーション
====================================
既存データを保持したまま、スキーマとシードデータを差分更新します。

使い方:
  python migrate_db.py          # 差分マイグレーションを実行
  python migrate_db.py --status # 現在のマイグレーション状態を表示
  python migrate_db.py --backup # バックアップのみ作成
"""

import sqlite3
import os
import sys
import shutil
from datetime import datetime
from werkzeug.security import generate_password_hash
import re
import unicodedata
import pykakasi
import argparse

# Windows環境での日本語出力対応
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = 'lms.db'
BACKUP_DIR = 'db_backups'

# pykakasi インスタンス（シングルトン）
_kakasi = None

def get_kakasi():
    global _kakasi
    if _kakasi is None:
        _kakasi = pykakasi.kakasi()
    return _kakasi

def generate_slug(title, existing_slugs=None):
    """タイトルからURLスラッグを生成"""
    text = unicodedata.normalize('NFKC', title)
    kakasi = get_kakasi()
    result = kakasi.convert(text)
    slug = '-'.join([item['hepburn'] for item in result if item['hepburn'].strip()])
    slug = slug.lower()
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    if not slug:
        slug = 'item'
    if existing_slugs:
        base_slug = slug
        counter = 2
        while slug in existing_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1
    return slug


# ============================================================
# ユーティリティ関数
# ============================================================

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def table_exists(cursor, table_name):
    """テーブルが存在するか確認"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None


def column_exists(cursor, table_name, column_name):
    """テーブルにカラムが存在するか確認"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns


def row_exists(cursor, table_name, where_clause, params):
    """指定条件のレコードが存在するか確認"""
    cursor.execute(f"SELECT 1 FROM {table_name} WHERE {where_clause} LIMIT 1", params)
    return cursor.fetchone() is not None


def create_backup():
    """データベースのバックアップを作成"""
    if not os.path.exists(DB_PATH):
        print("  データベースが存在しないため、バックアップはスキップ")
        return None
    
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'lms_backup_{timestamp}.db')
    shutil.copy2(DB_PATH, backup_path)
    print(f"  バックアップを作成しました: {backup_path}")
    return backup_path


# ============================================================
# マイグレーションバージョン管理
# ============================================================

def ensure_migration_table(cursor):
    """マイグレーション管理テーブルを作成"""
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        description TEXT NOT NULL,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')


def get_current_version(cursor):
    """現在のマイグレーションバージョンを取得"""
    if not table_exists(cursor, 'schema_migrations'):
        return 0
    cursor.execute("SELECT MAX(version) FROM schema_migrations")
    result = cursor.fetchone()
    return result[0] if result[0] is not None else 0


def mark_migration(cursor, version, description):
    """マイグレーションを適用済みとして記録"""
    cursor.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)",
        (version, description)
    )


# ============================================================
# マイグレーション定義
# ============================================================

def migration_001_base_tables(cursor):
    """基本テーブル（industries, users, categories, videos, progress, etc.）"""
    
    # Industries
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS industries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        name_en TEXT NOT NULL,
        description TEXT,
        icon TEXT DEFAULT 'bi-building',
        color TEXT DEFAULT '#667eea',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Users
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        industry_id INTEGER,
        company_name TEXT,
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (industry_id) REFERENCES industries (id)
    )
    ''')
    
    # Categories
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        slug TEXT UNIQUE,
        description TEXT,
        icon TEXT DEFAULT 'bi-folder',
        color TEXT DEFAULT '#667eea',
        parent_id INTEGER,
        display_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (parent_id) REFERENCES categories (id)
    )
    ''')
    
    # Videos
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE,
        description TEXT,
        summary TEXT,
        filename TEXT NOT NULL,
        category_id INTEGER,
        uploaded_by INTEGER,
        transcription_status TEXT DEFAULT 'none',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories (id),
        FOREIGN KEY (uploaded_by) REFERENCES users (id)
    )
    ''')
    
    # Progress
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS progress (
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
    
    # Category_Industry_Access
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS category_industry_access (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL,
        industry_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories (id),
        FOREIGN KEY (industry_id) REFERENCES industries (id),
        UNIQUE(category_id, industry_id)
    )
    ''')
    
    # Video_Transcripts
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_transcripts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        content_type TEXT DEFAULT 'description',
        timestamp_start REAL,
        timestamp_end REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (video_id) REFERENCES videos (id)
    )
    ''')
    
    # Industry_Usecases
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS industry_usecases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        industry_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        keywords TEXT,
        example_prompt TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (industry_id) REFERENCES industries (id)
    )
    ''')
    
    # Chat_History
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        response TEXT NOT NULL,
        recommended_videos TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # videos テーブルにカラムが不足していれば追加
    if not column_exists(cursor, 'videos', 'transcription_status'):
        cursor.execute("ALTER TABLE videos ADD COLUMN transcription_status TEXT DEFAULT 'none'")
    if not column_exists(cursor, 'videos', 'summary'):
        cursor.execute("ALTER TABLE videos ADD COLUMN summary TEXT")
    if not column_exists(cursor, 'videos', 'slug'):
        cursor.execute("ALTER TABLE videos ADD COLUMN slug TEXT UNIQUE")
    
    # categories テーブルにslugが不足していれば追加
    if not column_exists(cursor, 'categories', 'slug'):
        cursor.execute("ALTER TABLE categories ADD COLUMN slug TEXT UNIQUE")


def migration_002_tenant_department_role(cursor):
    """テナント・部署・ロール対応"""
    
    # Tenants
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
    
    # Departments
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
    
    # Access_Logs
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
    
    # Users テーブルにカラム追加
    if not column_exists(cursor, 'users', 'tenant_id'):
        cursor.execute("ALTER TABLE users ADD COLUMN tenant_id INTEGER REFERENCES tenants(id)")
    
    if not column_exists(cursor, 'users', 'department_id'):
        cursor.execute("ALTER TABLE users ADD COLUMN department_id INTEGER REFERENCES departments(id)")
    
    if not column_exists(cursor, 'users', 'role'):
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
        # 既存の is_admin=1 のユーザーを super_admin に移行
        cursor.execute("UPDATE users SET role = 'super_admin' WHERE is_admin = 1")


def migration_003_seed_industries(cursor):
    """業種マスタのシードデータ"""
    industries_data = [
        ('宿泊', 'Accommodation', '宿泊業・ホテル・旅館', 'bi-house-door', '#e63946'),
        ('小売', 'Retail', '小売業・販売業', 'bi-shop', '#f4a261'),
        ('飲食', 'Food and Beverage', '飲食業・レストラン・カフェ', 'bi-cup-hot', '#2a9d8f'),
        ('介護', 'Nursing Care', '介護・福祉サービス', 'bi-heart-pulse', '#e76f51'),
        ('医療', 'Medical Care', '医療・ヘルスケア', 'bi-hospital', '#264653'),
        ('教育', 'Education', '教育・研修サービス', 'bi-mortarboard', '#8338ec'),
    ]
    
    for name, name_en, desc, icon, color in industries_data:
        if not row_exists(cursor, 'industries', 'name = ?', (name,)):
            cursor.execute('''
            INSERT INTO industries (name, name_en, description, icon, color) VALUES (?, ?, ?, ?, ?)
            ''', (name, name_en, desc, icon, color))
            print(f"    業種追加: {name}")


def migration_004_seed_tenants(cursor):
    """サンプルテナントのシードデータ"""
    # 業種IDを取得
    def get_industry_id(name):
        cursor.execute("SELECT id FROM industries WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row[0] if row else None
    
    tenants_data = [
        ('グランドホテル東京', '宿泊'),
        ('湯元旅館', '宿泊'),
        ('スーパーマート', '小売'),
        ('ファッションストア', '小売'),
        ('さくらレストラン', '飲食'),
        ('スマイルケアセンター', '介護'),
        ('セントラルクリニック', '医療'),
        ('ブライトアカデミー', '教育'),
    ]
    
    for name, industry_name in tenants_data:
        if not row_exists(cursor, 'tenants', 'name = ?', (name,)):
            ind_id = get_industry_id(industry_name)
            cursor.execute('INSERT INTO tenants (name, industry_id) VALUES (?, ?)', (name, ind_id))
            print(f"    テナント追加: {name}")


def migration_005_seed_departments(cursor):
    """サンプル部署のシードデータ"""
    def get_tenant_id(name):
        cursor.execute("SELECT id FROM tenants WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row[0] if row else None
    
    departments_data = [
        ('グランドホテル東京', 'フロント課', None),
        ('グランドホテル東京', '営業部', None),
        ('スーパーマート', '販売部', None),
        ('スーパーマート', 'バイヤー部', None),
    ]
    
    for tenant_name, dept_name, parent_name in departments_data:
        tenant_id = get_tenant_id(tenant_name)
        if tenant_id and not row_exists(cursor, 'departments', 'tenant_id = ? AND name = ?', (tenant_id, dept_name)):
            parent_id = None
            if parent_name:
                cursor.execute("SELECT id FROM departments WHERE tenant_id = ? AND name = ?", (tenant_id, parent_name))
                parent_row = cursor.fetchone()
                parent_id = parent_row[0] if parent_row else None
            cursor.execute('INSERT INTO departments (tenant_id, name, parent_department_id) VALUES (?, ?, ?)',
                         (tenant_id, dept_name, parent_id))
            print(f"    部署追加: {tenant_name} > {dept_name}")


def migration_006_seed_users(cursor):
    """サンプルユーザーのシードデータ"""
    def get_industry_id(name):
        cursor.execute("SELECT id FROM industries WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row[0] if row else None
    
    def get_tenant_id(name):
        cursor.execute("SELECT id FROM tenants WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row[0] if row else None
    
    def get_department_id(tenant_name, dept_name):
        tenant_id = get_tenant_id(tenant_name)
        if not tenant_id or not dept_name:
            return None
        cursor.execute("SELECT id FROM departments WHERE tenant_id = ? AND name = ?", (tenant_id, dept_name))
        row = cursor.fetchone()
        return row[0] if row else None
    
    users_data = [
        # (username, email, password, industry, tenant, department, company, role, is_admin)
        ('admin', 'admin@example.com', 'admin123', None, None, None, None, 'super_admin', 1),
        ('hotel_tanaka', 'tanaka@grandhotel.co.jp', 'user123', '宿泊', 'グランドホテル東京', ('グランドホテル東京', 'フロント課'), 'グランドホテル東京', 'company_admin', 0),
        ('ryokan_suzuki', 'suzuki@yumoto-ryokan.jp', 'user123', '宿泊', '湯元旅館', None, '湯元旅館', 'user', 0),
        ('retail_yamada', 'yamada@supermart.co.jp', 'user123', '小売', 'スーパーマート', ('スーパーマート', '販売部'), 'スーパーマート', 'company_admin', 0),
        ('shop_sato', 'sato@fashion-store.jp', 'user123', '小売', 'ファッションストア', None, 'ファッションストア', 'user', 0),
        ('restaurant_ito', 'ito@sakura-restaurant.jp', 'user123', '飲食', 'さくらレストラン', None, 'さくらレストラン', 'user', 0),
        ('care_watanabe', 'watanabe@smile-care.jp', 'user123', '介護', 'スマイルケアセンター', None, 'スマイルケアセンター', 'user', 0),
        ('medical_takahashi', 'takahashi@central-clinic.jp', 'user123', '医療', 'セントラルクリニック', None, 'セントラルクリニック', 'user', 0),
        ('edu_kobayashi', 'kobayashi@bright-academy.jp', 'user123', '教育', 'ブライトアカデミー', None, 'ブライトアカデミー', 'user', 0),
    ]
    
    for username, email, password, industry, tenant, dept_info, company, role, is_admin in users_data:
        if not row_exists(cursor, 'users', 'username = ?', (username,)):
            ind_id = get_industry_id(industry) if industry else None
            ten_id = get_tenant_id(tenant) if tenant else None
            dept_id = None
            if dept_info:
                dept_id = get_department_id(dept_info[0], dept_info[1])
            
            cursor.execute('''
            INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, 
                             company_name, role, is_admin)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (username, email, generate_password_hash(password), ind_id, ten_id, dept_id,
                  company, role, is_admin))
            print(f"    ユーザー追加: {username}")


def migration_007_seed_categories(cursor):
    """サンプルカテゴリーのシードデータ"""
    used_slugs = set()
    
    # 既存のスラッグを収集
    cursor.execute("SELECT slug FROM categories WHERE slug IS NOT NULL")
    for row in cursor.fetchall():
        used_slugs.add(row[0])
    
    def insert_category_if_not_exists(name, desc, icon, color, parent_name, order):
        """カテゴリーが存在しなければ挿入"""
        # 同名カテゴリーが存在するか確認
        if parent_name:
            cursor.execute("SELECT id FROM categories WHERE name = ?", (parent_name,))
            parent_row = cursor.fetchone()
            parent_id = parent_row[0] if parent_row else None
        else:
            parent_id = None
        
        # 同名+同親のカテゴリーが存在するか確認
        if parent_id is not None:
            cursor.execute("SELECT id FROM categories WHERE name = ? AND parent_id = ?", (name, parent_id))
        else:
            cursor.execute("SELECT id FROM categories WHERE name = ? AND parent_id IS NULL", (name,))
        
        existing = cursor.fetchone()
        if existing:
            return existing[0]
        
        slug = generate_slug(name, used_slugs)
        used_slugs.add(slug)
        cursor.execute('''
        INSERT INTO categories (name, slug, description, icon, color, parent_id, display_order)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, slug, desc, icon, color, parent_id, order))
        print(f"    カテゴリー追加: {name}")
        return cursor.lastrowid
    
    # 全業種公開カテゴリー
    basic_id = insert_category_if_not_exists('基礎編', 'Rakuten AI for Businessの基本的な使い方を学ぶ', 'bi-book', '#667eea', None, 1)
    advanced_id = insert_category_if_not_exists('応用編', '業務での実践的な活用方法を学ぶ', 'bi-lightbulb', '#764ba2', None, 2)
    practical_id = insert_category_if_not_exists('実践編', '実際の事例やワークショップ', 'bi-briefcase', '#f093fb', None, 3)
    
    # サブカテゴリー（基礎編）
    insert_category_if_not_exists('プロンプト入門', 'プロンプトの基本と効果的な書き方', 'bi-chat-dots', '#667eea', '基礎編', 1)
    insert_category_if_not_exists('基本操作ガイド', 'AI for Businessの基本的な操作方法', 'bi-gear', '#667eea', '基礎編', 2)
    
    # サブカテゴリー（応用編）
    insert_category_if_not_exists('業務活用術', '日常業務でのAI活用テクニック', 'bi-graph-up', '#764ba2', '応用編', 1)
    insert_category_if_not_exists('データ分析活用', 'データ分析でのAI活用方法', 'bi-bar-chart', '#764ba2', '応用編', 2)
    
    # サブカテゴリー（実践編）
    insert_category_if_not_exists('事例紹介', '社内での活用事例を紹介', 'bi-collection', '#f093fb', '実践編', 1)
    insert_category_if_not_exists('ワークショップ', '実践的なハンズオンワークショップ', 'bi-people', '#f093fb', '実践編', 2)
    
    # 業種別カテゴリー
    accommodation_cat_id = insert_category_if_not_exists('宿泊業向けAI活用', '宿泊業・ホテル・旅館向けAI活用トレーニング', 'bi-house-door', '#e63946', None, 10)
    insert_category_if_not_exists('予約管理の効率化', 'AIを活用した予約管理と顧客対応', 'bi-calendar-check', '#e63946', '宿泊業向けAI活用', 1)
    insert_category_if_not_exists('多言語対応', '外国人観光客対応のAI活用', 'bi-globe', '#e63946', '宿泊業向けAI活用', 2)
    
    retail_cat_id = insert_category_if_not_exists('小売業向けAI活用', '小売・販売業向けAI活用トレーニング', 'bi-shop', '#f4a261', None, 11)
    insert_category_if_not_exists('在庫管理の最適化', 'AIを活用した在庫管理と需要予測', 'bi-box-seam', '#f4a261', '小売業向けAI活用', 1)
    
    food_cat_id = insert_category_if_not_exists('飲食業向けAI活用', '飲食業向けAI活用トレーニング', 'bi-cup-hot', '#2a9d8f', None, 12)
    insert_category_if_not_exists('メニュー開発支援', 'AIを活用したメニュー開発とレシピ提案', 'bi-journal-text', '#2a9d8f', '飲食業向けAI活用', 1)
    
    nursing_cat_id = insert_category_if_not_exists('介護業向けAI活用', '介護・福祉向けAI活用トレーニング', 'bi-heart-pulse', '#e76f51', None, 13)
    insert_category_if_not_exists('ケアプラン作成支援', 'AIを活用したケアプラン作成', 'bi-clipboard-heart', '#e76f51', '介護業向けAI活用', 1)
    
    medical_cat_id = insert_category_if_not_exists('医療業向けAI活用', '医療・ヘルスケア向けAI活用トレーニング', 'bi-hospital', '#264653', None, 14)
    insert_category_if_not_exists('医療文書作成支援', 'AIを活用した医療文書・レポート作成', 'bi-file-medical', '#264653', '医療業向けAI活用', 1)
    
    education_cat_id = insert_category_if_not_exists('教育業向けAI活用', '教育・研修向けAI活用トレーニング', 'bi-mortarboard', '#8338ec', None, 15)
    insert_category_if_not_exists('教材作成支援', 'AIを活用した教材・カリキュラム作成', 'bi-journal-bookmark', '#8338ec', '教育業向けAI活用', 1)
    
    # カテゴリーアクセス制御
    industry_category_pairs = [
        ('宿泊業向けAI活用', '宿泊'),
        ('小売業向けAI活用', '小売'),
        ('飲食業向けAI活用', '飲食'),
        ('介護業向けAI活用', '介護'),
        ('医療業向けAI活用', '医療'),
        ('教育業向けAI活用', '教育'),
    ]
    
    for cat_name, ind_name in industry_category_pairs:
        cursor.execute("SELECT id FROM categories WHERE name = ? AND parent_id IS NULL", (cat_name,))
        cat_row = cursor.fetchone()
        cursor.execute("SELECT id FROM industries WHERE name = ?", (ind_name,))
        ind_row = cursor.fetchone()
        if cat_row and ind_row:
            if not row_exists(cursor, 'category_industry_access', 
                            'category_id = ? AND industry_id = ?', (cat_row[0], ind_row[0])):
                cursor.execute('INSERT INTO category_industry_access (category_id, industry_id) VALUES (?, ?)',
                             (cat_row[0], ind_row[0]))
                print(f"    アクセス制御追加: {cat_name} → {ind_name}")


def migration_008_seed_usecases(cursor):
    """業種別ユースケースのシードデータ"""
    def get_industry_id(name):
        cursor.execute("SELECT id FROM industries WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row[0] if row else None
    
    usecases_data = [
        ('宿泊', '予約メール自動返信', '予約問い合わせに対する自動返信メールの生成', 
         '予約,メール,返信,自動化', '以下の予約問い合わせに対して、丁寧な返信メールを作成してください：'),
        ('宿泊', '多言語対応', '外国人観光客向けの多言語案内文の生成', 
         '翻訳,多言語,インバウンド,観光', 'ホテルの館内案内を英語と中国語に翻訳してください：'),
        ('宿泊', '口コミ返信作成', 'レビューサイトへの返信文の作成', 
         '口コミ,レビュー,返信,顧客対応', 'このお客様レビューに対する適切な返信を作成してください：'),
        ('小売', '商品説明文作成', 'ECサイト向け商品説明文の自動生成', 
         '商品説明,EC,コピーライティング', 'この商品の魅力的な説明文を作成してください：'),
        ('小売', '在庫管理レポート', '在庫状況の分析レポート作成', 
         '在庫,分析,レポート,需要予測', '以下の在庫データから分析レポートを作成してください：'),
        ('小売', 'お客様対応FAQ', 'よくある質問への回答作成', 
         'FAQ,顧客対応,問い合わせ', 'このお客様の問い合わせに対する回答を作成してください：'),
        ('飲食', 'メニュー開発アイデア', '新メニューのアイデア提案', 
         'メニュー,レシピ,開発,季節', '秋の新メニューのアイデアを5つ提案してください：'),
        ('飲食', 'SNS投稿文作成', '料理写真に添えるSNS投稿文の作成', 
         'SNS,Instagram,投稿,ハッシュタグ', 'この料理写真に合うInstagram投稿文を作成してください：'),
        ('飲食', 'アレルギー対応案内', 'アレルギー情報の説明文作成', 
         'アレルギー,食材,対応,説明', 'メニューのアレルギー情報を分かりやすく説明してください：'),
        ('介護', 'ケアプラン作成支援', '利用者情報からのケアプラン素案作成', 
         'ケアプラン,介護計画,アセスメント', 'この利用者情報からケアプランの素案を作成してください：'),
        ('介護', '家族への報告書作成', '利用者の状況報告書の作成', 
         '報告書,家族,状況報告', '今月の利用者の様子を家族向け報告書にまとめてください：'),
        ('介護', '記録文書の効率化', '介護記録の文章化支援', 
         '記録,文書化,効率化', '以下のメモから正式な介護記録を作成してください：'),
        ('医療', '患者説明資料作成', '患者向け説明資料の作成', 
         '患者説明,資料,分かりやすい', 'この治療法について患者さんに分かりやすく説明してください：'),
        ('医療', '医療文書サマリー', '医療文書の要約作成', 
         '要約,サマリー,カルテ', 'この医療記録の要約を作成してください：'),
        ('医療', '問診票の分析', '問診情報の整理と分析', 
         '問診,分析,症状', '以下の問診情報から重要なポイントを整理してください：'),
        ('教育', '教材作成支援', '授業用教材の作成', 
         '教材,授業,カリキュラム', 'このトピックについて中学生向けの教材を作成してください：'),
        ('教育', 'テスト問題作成', '理解度確認テストの作成', 
         'テスト,問題,評価', 'この単元の理解度を確認するテスト問題を作成してください：'),
        ('教育', '保護者向け通知作成', '保護者への連絡文書作成', 
         '保護者,通知,連絡', '以下の内容を保護者向けにお知らせ文書にしてください：'),
    ]
    
    for ind_name, title, desc, keywords, example in usecases_data:
        ind_id = get_industry_id(ind_name)
        if ind_id and not row_exists(cursor, 'industry_usecases', 
                                      'industry_id = ? AND title = ?', (ind_id, title)):
            cursor.execute('''
            INSERT INTO industry_usecases (industry_id, title, description, keywords, example_prompt)
            VALUES (?, ?, ?, ?, ?)
            ''', (ind_id, title, desc, keywords, example))
            print(f"    ユースケース追加: [{ind_name}] {title}")


def migration_009_generate_slugs(cursor):
    """既存データにスラッグがない場合に自動生成"""
    # カテゴリーのスラッグ生成
    cursor.execute("SELECT id, name FROM categories WHERE slug IS NULL")
    categories = cursor.fetchall()
    if categories:
        existing_slugs = set()
        cursor.execute("SELECT slug FROM categories WHERE slug IS NOT NULL")
        for row in cursor.fetchall():
            existing_slugs.add(row[0])
        
        for cat in categories:
            slug = generate_slug(cat[1], existing_slugs)
            existing_slugs.add(slug)
            cursor.execute("UPDATE categories SET slug = ? WHERE id = ?", (slug, cat[0]))
            print(f"    スラッグ生成: categories #{cat[0]} → {slug}")
    
    # 動画のスラッグ生成
    cursor.execute("SELECT id, title FROM videos WHERE slug IS NULL")
    videos = cursor.fetchall()
    if videos:
        existing_slugs = set()
        cursor.execute("SELECT slug FROM videos WHERE slug IS NOT NULL")
        for row in cursor.fetchall():
            existing_slugs.add(row[0])
        
        for video in videos:
            slug = generate_slug(video[1], existing_slugs)
            existing_slugs.add(slug)
            cursor.execute("UPDATE videos SET slug = ? WHERE id = ?", (slug, video[0]))
            print(f"    スラッグ生成: videos #{video[0]} → {slug}")


def migration_010_assign_tenant_role_to_existing_users(cursor):
    """既存ユーザーにテナント/部署/ロールを割り当て（データ移行）"""
    
    def get_tenant_id(name):
        cursor.execute("SELECT id FROM tenants WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row[0] if row else None
    
    def get_department_id(tenant_name, dept_name):
        tenant_id = get_tenant_id(tenant_name)
        if not tenant_id or not dept_name:
            return None
        cursor.execute("SELECT id FROM departments WHERE tenant_id = ? AND name = ?", (tenant_id, dept_name))
        row = cursor.fetchone()
        return row[0] if row else None
    
    # 既存ユーザーのマッピング定義
    # (username, tenant_name, department_info, role)
    user_assignments = [
        ('admin', None, None, 'super_admin'),
        ('hotel_tanaka', 'グランドホテル東京', ('グランドホテル東京', 'フロント課'), 'company_admin'),
        ('ryokan_suzuki', '湯元旅館', None, 'user'),
        ('retail_yamada', 'スーパーマート', ('スーパーマート', '販売部'), 'company_admin'),
        ('shop_sato', 'ファッションストア', None, 'user'),
        ('restaurant_ito', 'さくらレストラン', None, 'user'),
        ('care_watanabe', 'スマイルケアセンター', None, 'user'),
        ('medical_takahashi', 'セントラルクリニック', None, 'user'),
        ('edu_kobayashi', 'ブライトアカデミー', None, 'user'),
    ]
    
    for username, tenant_name, dept_info, role in user_assignments:
        # そのユーザーが存在し、かつ tenant_id が未設定の場合のみ更新
        cursor.execute("SELECT id, tenant_id, role FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if not user:
            continue
        
        user_id = user[0]
        current_tenant_id = user[1]
        current_role = user[2]
        
        needs_update = False
        updates = []
        params = []
        
        # テナント割当
        if tenant_name and current_tenant_id is None:
            ten_id = get_tenant_id(tenant_name)
            if ten_id:
                updates.append("tenant_id = ?")
                params.append(ten_id)
                needs_update = True
        
        # 部署割当
        if dept_info:
            dept_id = get_department_id(dept_info[0], dept_info[1])
            if dept_id:
                cursor.execute("SELECT department_id FROM users WHERE id = ?", (user_id,))
                current_dept = cursor.fetchone()
                if current_dept and current_dept[0] is None:
                    updates.append("department_id = ?")
                    params.append(dept_id)
                    needs_update = True
        
        # ロール割当（roleが'user'のままで本来は違うロールの場合）
        if role != 'user' and (current_role is None or current_role == 'user'):
            updates.append("role = ?")
            params.append(role)
            needs_update = True
        
        if needs_update:
            params.append(user_id)
            sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(sql, params)
            print(f"    ユーザー更新: {username} → role={role}, tenant={tenant_name}")


# ============================================================
# マイグレーション登録
# ============================================================

def migration_011_cleanup_test_data(cursor):
    """テスト実行で蓄積されたゴミデータをクリーンアップ"""
    
    # テスト由来の業種を削除
    cursor.execute("""
        DELETE FROM industries 
        WHERE name LIKE 'テスト業種%' OR name = '不正な業種'
    """)
    deleted = cursor.rowcount
    if deleted:
        print(f"    テスト業種を削除: {deleted}件")
    
    # テスト由来のユーザーを削除（progressも連鎖削除が必要）
    cursor.execute("""
        DELETE FROM progress WHERE user_id IN (
            SELECT id FROM users 
            WHERE username LIKE 'test_%' OR username LIKE 'csv_test_%' OR username = 'unauthorized_user'
        )
    """)
    cursor.execute("""
        DELETE FROM chat_history WHERE user_id IN (
            SELECT id FROM users 
            WHERE username LIKE 'test_%' OR username LIKE 'csv_test_%' OR username = 'unauthorized_user'
        )
    """)
    cursor.execute("""
        DELETE FROM access_logs WHERE user_id IN (
            SELECT id FROM users 
            WHERE username LIKE 'test_%' OR username LIKE 'csv_test_%' OR username = 'unauthorized_user'
        )
    """)
    cursor.execute("""
        DELETE FROM users 
        WHERE username LIKE 'test_%' OR username LIKE 'csv_test_%' OR username = 'unauthorized_user'
    """)
    deleted = cursor.rowcount
    if deleted:
        print(f"    テストユーザーを削除: {deleted}件")
    
    # テスト由来のテナントを削除
    cursor.execute("DELETE FROM tenants WHERE name = 'テストホテル'")
    deleted = cursor.rowcount
    if deleted:
        print(f"    テストテナントを削除: {deleted}件")
    
    # テスト由来の部署を削除
    cursor.execute("""
        DELETE FROM departments 
        WHERE name IN ('テスト部署', '更新後の部署名', '更新テスト部署', '削除テスト部署')
    """)
    deleted = cursor.rowcount
    if deleted:
        print(f"    テスト部署を削除: {deleted}件")
    
    # テスト由来のカテゴリーを削除
    cursor.execute("""
        DELETE FROM category_industry_access WHERE category_id IN (
            SELECT id FROM categories WHERE name IN ('テストカテゴリー', 'アクセステスト用')
        )
    """)
    cursor.execute("""
        DELETE FROM categories 
        WHERE name IN ('テストカテゴリー', 'アクセステスト用')
    """)
    deleted = cursor.rowcount
    if deleted:
        print(f"    テストカテゴリーを削除: {deleted}件")


def migration_012_ensure_company_admins(cursor):
    """全テナントに最低1名のcompany_adminを確保"""
    
    # company_adminがいないテナントを検索
    cursor.execute("""
        SELECT t.id, t.name, t.industry_id
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM users u 
            WHERE u.tenant_id = t.id 
              AND u.role = 'company_admin'
        )
    """)
    orphan_tenants = cursor.fetchall()
    
    if not orphan_tenants:
        print("    全テナントにcompany_adminが存在します（変更なし）")
        return
    
    # テナントごとにcompany_adminを追加
    admin_accounts = {
        '湯元旅館':           ('ryokan_admin',   'admin@yumoto-ryokan.jp'),
        'ファッションストア': ('fashion_admin',   'admin@fashion-store.jp'),
        'さくらレストラン':   ('sakura_admin',    'admin@sakura-restaurant.jp'),
        'スマイルケアセンター': ('care_admin',     'admin@smile-care.jp'),
        'セントラルクリニック': ('medical_admin',  'admin@central-clinic.jp'),
        'ブライトアカデミー':   ('edu_admin',      'admin@bright-academy.jp'),
    }
    
    for tenant_id, tenant_name, industry_id in orphan_tenants:
        if tenant_name in admin_accounts:
            username, email = admin_accounts[tenant_name]
        else:
            # 汎用的なフォールバック
            safe_name = tenant_name.replace(' ', '_')[:20]
            username = f'admin_{safe_name}_{tenant_id}'
            email = f'admin_tenant{tenant_id}@example.com'
        
        # 既存ユーザーと重複しないかチェック
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            print(f"    {tenant_name}: {username} は既に存在（スキップ）")
            continue
        
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            print(f"    {tenant_name}: {email} は既に存在（スキップ）")
            continue
        
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, industry_id, tenant_id, 
                             company_name, role, is_admin)
            VALUES (?, ?, ?, ?, ?, ?, 'company_admin', 0)
        ''', (username, email, generate_password_hash('user123'),
              industry_id, tenant_id, tenant_name))
        print(f"    company_admin追加: {username} ({tenant_name})")


def migration_013_video_qa_tables(cursor):
    """動画Q&A（質問・回答）テーブルを作成"""
    # 質問テーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        tenant_id INTEGER,
        question_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (video_id) REFERENCES videos (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id) REFERENCES tenants (id)
    )
    ''')
    # 回答テーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        answer_text TEXT NOT NULL,
        is_admin_answer INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (question_id) REFERENCES video_questions (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    ''')
    print("    video_questions, video_answers テーブルを作成しました")


def migration_014_announcements_table(cursor):
    """お知らせ・通知テーブルを作成"""
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        type TEXT DEFAULT 'info',
        target_tenant_id INTEGER,
        is_active INTEGER DEFAULT 1,
        publish_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (author_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (target_tenant_id) REFERENCES tenants (id)
    )
    ''')
    print("    announcements テーブルを作成しました")


MIGRATIONS = [
    (1, '基本テーブル作成', migration_001_base_tables),
    (2, 'テナント・部署・ロール対応', migration_002_tenant_department_role),
    (3, '業種マスタ シードデータ', migration_003_seed_industries),
    (4, 'テナント シードデータ', migration_004_seed_tenants),
    (5, '部署 シードデータ', migration_005_seed_departments),
    (6, 'ユーザー シードデータ', migration_006_seed_users),
    (7, 'カテゴリー シードデータ', migration_007_seed_categories),
    (8, 'ユースケース シードデータ', migration_008_seed_usecases),
    (9, 'スラッグ自動生成', migration_009_generate_slugs),
    (10, '既存ユーザーにテナント/ロール割り当て', migration_010_assign_tenant_role_to_existing_users),
    (11, 'テストデータのクリーンアップ', migration_011_cleanup_test_data),
    (12, '全テナントにcompany_admin確保', migration_012_ensure_company_admins),
    (13, '動画Q&Aテーブル作成', migration_013_video_qa_tables),
    (14, 'お知らせテーブル作成', migration_014_announcements_table),
]


# ============================================================
# メイン実行
# ============================================================

def run_migrations(verbose=True, db_path=None):
    """差分マイグレーションを実行"""
    if db_path is None:
        db_path = DB_PATH
    db_exists = os.path.exists(db_path)
    
    if verbose:
        print("\n" + "=" * 60)
        print("  LMS データベース差分マイグレーション")
        print("=" * 60)
    
    if db_exists:
        if verbose:
            print(f"\n  既存データベースを検出: {db_path}")
            # バックアップ作成（本番DBのみバックアップ）
            if db_path == DB_PATH:
                create_backup()
    else:
        if verbose:
            print(f"\n  新規データベースを作成: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # マイグレーションテーブル確認
    ensure_migration_table(cursor)
    current_version = get_current_version(cursor)
    
    if verbose:
        print(f"  現在のバージョン: {current_version}")
        print(f"  最新バージョン: {MIGRATIONS[-1][0]}")
    
    applied_count = 0
    
    for version, description, migration_func in MIGRATIONS:
        if version > current_version:
            if verbose:
                print(f"\n  [v{version}] {description} を適用中...")
            
            try:
                migration_func(cursor)
                mark_migration(cursor, version, description)
                conn.commit()
                applied_count += 1
                if verbose:
                    print(f"  [v{version}] ✓ 完了")
            except Exception as e:
                conn.rollback()
                print(f"\n  [v{version}] ✗ エラー: {e}")
                print(f"  マイグレーションを中断しました。データベースは変更されていません。")
                conn.close()
                return False
    
    # videosフォルダを作成
    os.makedirs('videos', exist_ok=True)
    
    conn.close()
    
    if verbose:
        if applied_count > 0:
            print(f"\n  {applied_count}件のマイグレーションを適用しました")
        else:
            print(f"\n  データベースは最新です。適用するマイグレーションはありません。")
        print("=" * 60 + "\n")
    
    return True


def show_status():
    """マイグレーション状態を表示"""
    print("\n" + "=" * 60)
    print("  マイグレーション状態")
    print("=" * 60)
    
    if not os.path.exists(DB_PATH):
        print("\n  データベースが存在しません。")
        print("  'python migrate_db.py' を実行して初期化してください。")
        print("=" * 60 + "\n")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    ensure_migration_table(cursor)
    
    # 適用済みマイグレーションを取得
    cursor.execute("SELECT version, description, applied_at FROM schema_migrations ORDER BY version")
    applied = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
    
    print()
    for version, description, _ in MIGRATIONS:
        if version in applied:
            desc, applied_at = applied[version]
            print(f"  ✓ v{version:02d} {description} (適用: {applied_at})")
        else:
            print(f"  ○ v{version:02d} {description} (未適用)")
    
    # テーブル別のレコード数
    print(f"\n  {'─' * 40}")
    print(f"  テーブル別レコード数:")
    tables = ['industries', 'tenants', 'departments', 'users', 'categories', 'videos', 
              'progress', 'industry_usecases', 'chat_history', 'access_logs', 
              'video_transcripts', 'category_industry_access']
    
    for table in tables:
        if table_exists(cursor, table):
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"    {table:30s} : {count:5d} 件")
        else:
            print(f"    {table:30s} : (テーブルなし)")
    
    conn.close()
    print("=" * 60 + "\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='LMS データベース差分マイグレーション')
    parser.add_argument('--status', action='store_true', help='マイグレーション状態を表示')
    parser.add_argument('--backup', action='store_true', help='バックアップのみ作成')
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.backup:
        create_backup()
    else:
        run_migrations()
