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
    
    # Industriesテーブル作成（業種マスタ）
    cursor.execute('''
    CREATE TABLE industries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        name_en TEXT NOT NULL,
        description TEXT,
        icon TEXT DEFAULT 'bi-building',
        color TEXT DEFAULT '#667eea',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Usersテーブル作成（industry_id, company_name追加）
    cursor.execute('''
    CREATE TABLE users (
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
    
    # Categoriesテーブル作成（階層構造対応）
    cursor.execute('''
    CREATE TABLE categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        icon TEXT DEFAULT 'bi-folder',
        color TEXT DEFAULT '#667eea',
        parent_id INTEGER,
        display_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (parent_id) REFERENCES categories (id)
    )
    ''')
    
    # Videosテーブル作成
    cursor.execute('''
    CREATE TABLE videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        filename TEXT NOT NULL,
        category_id INTEGER,
        uploaded_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories (id),
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
    
    # Category_Industry_Accessテーブル作成（カテゴリーの業種別アクセス制御）
    # このテーブルにレコードがないカテゴリーは「全業種公開」
    # レコードがある場合は、指定された業種のみアクセス可能
    cursor.execute('''
    CREATE TABLE category_industry_access (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL,
        industry_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories (id),
        FOREIGN KEY (industry_id) REFERENCES industries (id),
        UNIQUE(category_id, industry_id)
    )
    ''')
    
    # ========== 業種マスタを作成 ==========
    industries_data = [
        ('宿泊', 'Accommodation', '宿泊業・ホテル・旅館', 'bi-house-door', '#e63946'),
        ('小売', 'Retail', '小売業・販売業', 'bi-shop', '#f4a261'),
        ('飲食', 'Food and Beverage', '飲食業・レストラン・カフェ', 'bi-cup-hot', '#2a9d8f'),
        ('介護', 'Nursing Care', '介護・福祉サービス', 'bi-heart-pulse', '#e76f51'),
        ('医療', 'Medical Care', '医療・ヘルスケア', 'bi-hospital', '#264653'),
        ('教育', 'Education', '教育・研修サービス', 'bi-mortarboard', '#8338ec'),
    ]
    
    industry_ids = {}
    for name, name_en, desc, icon, color in industries_data:
        cursor.execute('''
        INSERT INTO industries (name, name_en, description, icon, color) VALUES (?, ?, ?, ?, ?)
        ''', (name, name_en, desc, icon, color))
        industry_ids[name] = cursor.lastrowid
    
    print("業種マスタを作成しました")
    
    # ========== サンプルユーザーを作成 ==========
    # 管理者アカウント（業種なし - 全アクセス可能）
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, company_name, is_admin)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('admin', 'admin@example.com', generate_password_hash('admin123'), None, None, 1))
    
    # 宿泊業ユーザー
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, company_name, is_admin)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('hotel_tanaka', 'tanaka@grandhotel.co.jp', generate_password_hash('user123'), 
          industry_ids['宿泊'], 'グランドホテル東京', 0))
    
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, company_name, is_admin)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('ryokan_suzuki', 'suzuki@yumoto-ryokan.jp', generate_password_hash('user123'), 
          industry_ids['宿泊'], '湯元旅館', 0))
    
    # 小売業ユーザー
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, company_name, is_admin)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('retail_yamada', 'yamada@supermart.co.jp', generate_password_hash('user123'), 
          industry_ids['小売'], 'スーパーマート', 0))
    
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, company_name, is_admin)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('shop_sato', 'sato@fashion-store.jp', generate_password_hash('user123'), 
          industry_ids['小売'], 'ファッションストア', 0))
    
    # 飲食業ユーザー
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, company_name, is_admin)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('restaurant_ito', 'ito@sakura-restaurant.jp', generate_password_hash('user123'), 
          industry_ids['飲食'], 'さくらレストラン', 0))
    
    # 介護業ユーザー
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, company_name, is_admin)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('care_watanabe', 'watanabe@smile-care.jp', generate_password_hash('user123'), 
          industry_ids['介護'], 'スマイルケアセンター', 0))
    
    # 医療業ユーザー
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, company_name, is_admin)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('medical_takahashi', 'takahashi@central-clinic.jp', generate_password_hash('user123'), 
          industry_ids['医療'], 'セントラルクリニック', 0))
    
    # 教育業ユーザー
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, company_name, is_admin)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('edu_kobayashi', 'kobayashi@bright-academy.jp', generate_password_hash('user123'), 
          industry_ids['教育'], 'ブライトアカデミー', 0))
    
    print("サンプルユーザーを作成しました")
    
    # ========== videosフォルダを作成 ==========
    os.makedirs('videos', exist_ok=True)
    
    # ========== サンプルカテゴリーを作成 ==========
    # 全業種公開カテゴリー
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('基礎編', 'Rakuten AI for Businessの基本的な使い方を学ぶ', 'bi-book', '#667eea', None, 1))
    basic_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('応用編', '業務での実践的な活用方法を学ぶ', 'bi-lightbulb', '#764ba2', None, 2))
    advanced_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('実践編', '実際の事例やワークショップ', 'bi-briefcase', '#f093fb', None, 3))
    practical_id = cursor.lastrowid
    
    # サブカテゴリー（基礎編）
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('プロンプト入門', 'プロンプトの基本と効果的な書き方', 'bi-chat-dots', '#667eea', basic_id, 1))
    prompt_intro_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('基本操作ガイド', 'AI for Businessの基本的な操作方法', 'bi-gear', '#667eea', basic_id, 2))
    
    # サブカテゴリー（応用編）
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('業務活用術', '日常業務でのAI活用テクニック', 'bi-graph-up', '#764ba2', advanced_id, 1))
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('データ分析活用', 'データ分析でのAI活用方法', 'bi-bar-chart', '#764ba2', advanced_id, 2))
    
    # サブカテゴリー（実践編）
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('事例紹介', '社内での活用事例を紹介', 'bi-collection', '#f093fb', practical_id, 1))
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('ワークショップ', '実践的なハンズオンワークショップ', 'bi-people', '#f093fb', practical_id, 2))
    
    # ========== 業種別カテゴリーを作成 ==========
    # 宿泊業向け
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('宿泊業向けAI活用', '宿泊業・ホテル・旅館向けAI活用トレーニング', 'bi-house-door', '#e63946', None, 10))
    accommodation_cat_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('予約管理の効率化', 'AIを活用した予約管理と顧客対応', 'bi-calendar-check', '#e63946', accommodation_cat_id, 1))
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('多言語対応', '外国人観光客対応のAI活用', 'bi-globe', '#e63946', accommodation_cat_id, 2))
    
    # 小売業向け
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('小売業向けAI活用', '小売・販売業向けAI活用トレーニング', 'bi-shop', '#f4a261', None, 11))
    retail_cat_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('在庫管理の最適化', 'AIを活用した在庫管理と需要予測', 'bi-box-seam', '#f4a261', retail_cat_id, 1))
    
    # 飲食業向け
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('飲食業向けAI活用', '飲食業向けAI活用トレーニング', 'bi-cup-hot', '#2a9d8f', None, 12))
    food_cat_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('メニュー開発支援', 'AIを活用したメニュー開発とレシピ提案', 'bi-journal-text', '#2a9d8f', food_cat_id, 1))
    
    # 介護業向け
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('介護業向けAI活用', '介護・福祉向けAI活用トレーニング', 'bi-heart-pulse', '#e76f51', None, 13))
    nursing_cat_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('ケアプラン作成支援', 'AIを活用したケアプラン作成', 'bi-clipboard-heart', '#e76f51', nursing_cat_id, 1))
    
    # 医療業向け
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('医療業向けAI活用', '医療・ヘルスケア向けAI活用トレーニング', 'bi-hospital', '#264653', None, 14))
    medical_cat_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('医療文書作成支援', 'AIを活用した医療文書・レポート作成', 'bi-file-medical', '#264653', medical_cat_id, 1))
    
    # 教育業向け
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('教育業向けAI活用', '教育・研修向けAI活用トレーニング', 'bi-mortarboard', '#8338ec', None, 15))
    education_cat_id = cursor.lastrowid
    
    cursor.execute('''
    INSERT INTO categories (name, description, icon, color, parent_id, display_order)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', ('教材作成支援', 'AIを活用した教材・カリキュラム作成', 'bi-journal-bookmark', '#8338ec', education_cat_id, 1))
    
    print("サンプルカテゴリーを作成しました")
    
    # ========== カテゴリーアクセス制御を設定 ==========
    # 基礎編、応用編、実践編 は全業種公開（レコードなし）
    
    # 業種別カテゴリーのアクセス制御
    industry_category_map = [
        (accommodation_cat_id, industry_ids['宿泊']),
        (retail_cat_id, industry_ids['小売']),
        (food_cat_id, industry_ids['飲食']),
        (nursing_cat_id, industry_ids['介護']),
        (medical_cat_id, industry_ids['医療']),
        (education_cat_id, industry_ids['教育']),
    ]
    
    for cat_id, ind_id in industry_category_map:
        cursor.execute('''
        INSERT INTO category_industry_access (category_id, industry_id) VALUES (?, ?)
        ''', (cat_id, ind_id))
    
    print("カテゴリーアクセス制御を設定しました")
    
    # ========== サンプル動画を登録 ==========
    sample_video = 'Rakuten AI for Businessのご紹介_1111_20260114_204516.mp4'
    if os.path.exists(sample_video):
        destination = os.path.join('videos', sample_video)
        if not os.path.exists(destination):
            shutil.copy(sample_video, destination)
            print(f"サンプル動画をコピーしました: {sample_video}")
        
        cursor.execute('''
        INSERT INTO videos (title, description, filename, category_id, uploaded_by)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            'Rakuten AI for Businessのご紹介',
            'Rakuten AI for Businessの機能と特徴を紹介する動画です。',
            sample_video,
            prompt_intro_id,
            1
        ))
    
    conn.commit()
    conn.close()
    
    # ========== 完了メッセージ ==========
    print("\n" + "=" * 60)
    print("  データベースの初期化が完了しました")
    print("=" * 60)
    
    print("\n【業種一覧】")
    for name, name_en, _, _, _ in industries_data:
        print(f"  ・{name}（{name_en}）")
    
    print("\n【アカウント一覧】")
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │ 管理者（全業種アクセス可能）                            │")
    print("  │   admin / admin123                                      │")
    print("  ├─────────────────────────────────────────────────────────┤")
    print("  │ 業種          ユーザー名           会社名               │")
    print("  ├─────────────────────────────────────────────────────────┤")
    print("  │ 宿泊          hotel_tanaka        グランドホテル東京    │")
    print("  │ 宿泊          ryokan_suzuki       湯元旅館              │")
    print("  │ 小売          retail_yamada       スーパーマート        │")
    print("  │ 小売          shop_sato           ファッションストア    │")
    print("  │ 飲食          restaurant_ito      さくらレストラン      │")
    print("  │ 介護          care_watanabe       スマイルケアセンター  │")
    print("  │ 医療          medical_takahashi   セントラルクリニック  │")
    print("  │ 教育          edu_kobayashi       ブライトアカデミー    │")
    print("  └─────────────────────────────────────────────────────────┘")
    print("  ※パスワードは全て user123")
    
    print("\n【カテゴリー構造とアクセス権】")
    print("  ├── 基礎編              [全業種公開]")
    print("  │   ├── プロンプト入門")
    print("  │   └── 基本操作ガイド")
    print("  ├── 応用編              [全業種公開]")
    print("  │   ├── 業務活用術")
    print("  │   └── データ分析活用")
    print("  ├── 実践編              [全業種公開]")
    print("  │   ├── 事例紹介")
    print("  │   └── ワークショップ")
    print("  ├── 宿泊業向けAI活用    [宿泊業のみ]")
    print("  ├── 小売業向けAI活用    [小売業のみ]")
    print("  ├── 飲食業向けAI活用    [飲食業のみ]")
    print("  ├── 介護業向けAI活用    [介護業のみ]")
    print("  ├── 医療業向けAI活用    [医療業のみ]")
    print("  └── 教育業向けAI活用    [教育業のみ]")
    print("\n" + "=" * 60 + "\n")

if __name__ == '__main__':
    init_database()
