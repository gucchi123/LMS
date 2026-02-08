import sqlite3
from werkzeug.security import generate_password_hash
import os
import shutil
import sys
import re
import unicodedata
import pykakasi
import argparse

# Windows環境での日本語出力対応
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# pykakasi インスタンス（シングルトン）
_kakasi = None

def get_kakasi():
    """pykakasi インスタンスを取得"""
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
    
    # Tenantsテーブル作成（会社/テナント管理）
    cursor.execute('''
    CREATE TABLE tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        industry_id INTEGER,
        logo TEXT,
        settings TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (industry_id) REFERENCES industries (id)
    )
    ''')
    
    # Departmentsテーブル作成（部署管理）
    cursor.execute('''
    CREATE TABLE departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        parent_department_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
        FOREIGN KEY (parent_department_id) REFERENCES departments (id)
    )
    ''')
    
    # Usersテーブル作成（tenant_id, department_id, role追加）
    cursor.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        industry_id INTEGER,
        tenant_id INTEGER,
        department_id INTEGER,
        company_name TEXT,
        role TEXT DEFAULT 'user',
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (industry_id) REFERENCES industries (id),
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
        FOREIGN KEY (department_id) REFERENCES departments (id)
    )
    ''')
    
    # Categoriesテーブル作成（階層構造対応・slug追加）
    cursor.execute('''
    CREATE TABLE categories (
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
    
    # Videosテーブル作成（slug追加、transcription_status追加）
    cursor.execute('''
    CREATE TABLE videos (
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
    
    # ========== AIチャット機能用テーブル ==========
    
    # Video_Transcriptsテーブル作成（動画の文字起こし・説明）
    cursor.execute('''
    CREATE TABLE video_transcripts (
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
    
    # Industry_Usecasesテーブル作成（業種別ユースケース）
    cursor.execute('''
    CREATE TABLE industry_usecases (
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
    
    # Chat_Historyテーブル作成（チャット履歴）
    cursor.execute('''
    CREATE TABLE chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        response TEXT NOT NULL,
        recommended_videos TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Access_Logsテーブル作成（カスタムアクセス分析）
    cursor.execute('''
    CREATE TABLE access_logs (
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
    
    # ========== サンプルテナントを作成 ==========
    tenants_data = [
        ('グランドホテル東京', industry_ids['宿泊']),
        ('湯元旅館', industry_ids['宿泊']),
        ('スーパーマート', industry_ids['小売']),
        ('ファッションストア', industry_ids['小売']),
        ('さくらレストラン', industry_ids['飲食']),
        ('スマイルケアセンター', industry_ids['介護']),
        ('セントラルクリニック', industry_ids['医療']),
        ('ブライトアカデミー', industry_ids['教育']),
    ]
    
    tenant_ids = {}
    for name, ind_id in tenants_data:
        cursor.execute('''
        INSERT INTO tenants (name, industry_id) VALUES (?, ?)
        ''', (name, ind_id))
        tenant_ids[name] = cursor.lastrowid
    
    print("サンプルテナントを作成しました")
    
    # ========== サンプル部署を作成 ==========
    # グランドホテル東京
    cursor.execute("INSERT INTO departments (tenant_id, name) VALUES (?, ?)", (tenant_ids['グランドホテル東京'], 'フロント課'))
    dept_front = cursor.lastrowid
    cursor.execute("INSERT INTO departments (tenant_id, name) VALUES (?, ?)", (tenant_ids['グランドホテル東京'], '営業部'))
    dept_sales_hotel = cursor.lastrowid
    
    # スーパーマート
    cursor.execute("INSERT INTO departments (tenant_id, name) VALUES (?, ?)", (tenant_ids['スーパーマート'], '販売部'))
    dept_sales_mart = cursor.lastrowid
    cursor.execute("INSERT INTO departments (tenant_id, name) VALUES (?, ?)", (tenant_ids['スーパーマート'], 'バイヤー部'))
    dept_buyer = cursor.lastrowid
    
    print("サンプル部署を作成しました")
    
    # ========== サンプルユーザーを作成 ==========
    # super_admin（楽天管理者 - 全テナント横断）
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('admin', 'admin@example.com', generate_password_hash('admin123'), None, None, None, None, 'super_admin', 1))
    
    # 宿泊業ユーザー（company_admin + user）
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('hotel_tanaka', 'tanaka@grandhotel.co.jp', generate_password_hash('user123'), 
          industry_ids['宿泊'], tenant_ids['グランドホテル東京'], dept_front, 'グランドホテル東京', 'company_admin', 0))
    
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('ryokan_suzuki', 'suzuki@yumoto-ryokan.jp', generate_password_hash('user123'), 
          industry_ids['宿泊'], tenant_ids['湯元旅館'], None, '湯元旅館', 'user', 0))
    
    # 小売業ユーザー（company_admin + user）
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('retail_yamada', 'yamada@supermart.co.jp', generate_password_hash('user123'), 
          industry_ids['小売'], tenant_ids['スーパーマート'], dept_sales_mart, 'スーパーマート', 'company_admin', 0))
    
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('shop_sato', 'sato@fashion-store.jp', generate_password_hash('user123'), 
          industry_ids['小売'], tenant_ids['ファッションストア'], None, 'ファッションストア', 'user', 0))
    
    # 飲食業ユーザー
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('restaurant_ito', 'ito@sakura-restaurant.jp', generate_password_hash('user123'), 
          industry_ids['飲食'], tenant_ids['さくらレストラン'], None, 'さくらレストラン', 'user', 0))
    
    # 介護業ユーザー
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('care_watanabe', 'watanabe@smile-care.jp', generate_password_hash('user123'), 
          industry_ids['介護'], tenant_ids['スマイルケアセンター'], None, 'スマイルケアセンター', 'user', 0))
    
    # 医療業ユーザー
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('medical_takahashi', 'takahashi@central-clinic.jp', generate_password_hash('user123'), 
          industry_ids['医療'], tenant_ids['セントラルクリニック'], None, 'セントラルクリニック', 'user', 0))
    
    # 教育業ユーザー
    cursor.execute('''
    INSERT INTO users (username, email, password_hash, industry_id, tenant_id, department_id, company_name, role, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('edu_kobayashi', 'kobayashi@bright-academy.jp', generate_password_hash('user123'), 
          industry_ids['教育'], tenant_ids['ブライトアカデミー'], None, 'ブライトアカデミー', 'user', 0))
    
    print("サンプルユーザーを作成しました")
    
    # ========== videosフォルダを作成 ==========
    os.makedirs('videos', exist_ok=True)
    
    # ========== サンプルカテゴリーを作成 ==========
    # スラッグ管理用セット
    used_slugs = set()
    
    def insert_category(name, desc, icon, color, parent_id, order):
        """カテゴリーを挿入し、自動でスラッグを生成"""
        slug = generate_slug(name, used_slugs)
        used_slugs.add(slug)
        cursor.execute('''
        INSERT INTO categories (name, slug, description, icon, color, parent_id, display_order)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, slug, desc, icon, color, parent_id, order))
        return cursor.lastrowid
    
    # 全業種公開カテゴリー
    basic_id = insert_category('基礎編', 'Rakuten AI for Businessの基本的な使い方を学ぶ', 'bi-book', '#667eea', None, 1)
    advanced_id = insert_category('応用編', '業務での実践的な活用方法を学ぶ', 'bi-lightbulb', '#764ba2', None, 2)
    practical_id = insert_category('実践編', '実際の事例やワークショップ', 'bi-briefcase', '#f093fb', None, 3)
    
    # サブカテゴリー（基礎編）
    prompt_intro_id = insert_category('プロンプト入門', 'プロンプトの基本と効果的な書き方', 'bi-chat-dots', '#667eea', basic_id, 1)
    insert_category('基本操作ガイド', 'AI for Businessの基本的な操作方法', 'bi-gear', '#667eea', basic_id, 2)
    
    # サブカテゴリー（応用編）
    insert_category('業務活用術', '日常業務でのAI活用テクニック', 'bi-graph-up', '#764ba2', advanced_id, 1)
    insert_category('データ分析活用', 'データ分析でのAI活用方法', 'bi-bar-chart', '#764ba2', advanced_id, 2)
    
    # サブカテゴリー（実践編）
    insert_category('事例紹介', '社内での活用事例を紹介', 'bi-collection', '#f093fb', practical_id, 1)
    insert_category('ワークショップ', '実践的なハンズオンワークショップ', 'bi-people', '#f093fb', practical_id, 2)
    
    # ========== 業種別カテゴリーを作成 ==========
    # 宿泊業向け
    accommodation_cat_id = insert_category('宿泊業向けAI活用', '宿泊業・ホテル・旅館向けAI活用トレーニング', 'bi-house-door', '#e63946', None, 10)
    insert_category('予約管理の効率化', 'AIを活用した予約管理と顧客対応', 'bi-calendar-check', '#e63946', accommodation_cat_id, 1)
    insert_category('多言語対応', '外国人観光客対応のAI活用', 'bi-globe', '#e63946', accommodation_cat_id, 2)
    
    # 小売業向け
    retail_cat_id = insert_category('小売業向けAI活用', '小売・販売業向けAI活用トレーニング', 'bi-shop', '#f4a261', None, 11)
    insert_category('在庫管理の最適化', 'AIを活用した在庫管理と需要予測', 'bi-box-seam', '#f4a261', retail_cat_id, 1)
    
    # 飲食業向け
    food_cat_id = insert_category('飲食業向けAI活用', '飲食業向けAI活用トレーニング', 'bi-cup-hot', '#2a9d8f', None, 12)
    insert_category('メニュー開発支援', 'AIを活用したメニュー開発とレシピ提案', 'bi-journal-text', '#2a9d8f', food_cat_id, 1)
    
    # 介護業向け
    nursing_cat_id = insert_category('介護業向けAI活用', '介護・福祉向けAI活用トレーニング', 'bi-heart-pulse', '#e76f51', None, 13)
    insert_category('ケアプラン作成支援', 'AIを活用したケアプラン作成', 'bi-clipboard-heart', '#e76f51', nursing_cat_id, 1)
    
    # 医療業向け
    medical_cat_id = insert_category('医療業向けAI活用', '医療・ヘルスケア向けAI活用トレーニング', 'bi-hospital', '#264653', None, 14)
    insert_category('医療文書作成支援', 'AIを活用した医療文書・レポート作成', 'bi-file-medical', '#264653', medical_cat_id, 1)
    
    # 教育業向け
    education_cat_id = insert_category('教育業向けAI活用', '教育・研修向けAI活用トレーニング', 'bi-mortarboard', '#8338ec', None, 15)
    insert_category('教材作成支援', 'AIを活用した教材・カリキュラム作成', 'bi-journal-bookmark', '#8338ec', education_cat_id, 1)
    
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
    
    # ========== 業種別ユースケースを登録 ==========
    usecases_data = [
        # 宿泊業
        (industry_ids['宿泊'], '予約メール自動返信', '予約問い合わせに対する自動返信メールの生成', 
         '予約,メール,返信,自動化', '以下の予約問い合わせに対して、丁寧な返信メールを作成してください：'),
        (industry_ids['宿泊'], '多言語対応', '外国人観光客向けの多言語案内文の生成', 
         '翻訳,多言語,インバウンド,観光', 'ホテルの館内案内を英語と中国語に翻訳してください：'),
        (industry_ids['宿泊'], '口コミ返信作成', 'レビューサイトへの返信文の作成', 
         '口コミ,レビュー,返信,顧客対応', 'このお客様レビューに対する適切な返信を作成してください：'),
        
        # 小売業
        (industry_ids['小売'], '商品説明文作成', 'ECサイト向け商品説明文の自動生成', 
         '商品説明,EC,コピーライティング', 'この商品の魅力的な説明文を作成してください：'),
        (industry_ids['小売'], '在庫管理レポート', '在庫状況の分析レポート作成', 
         '在庫,分析,レポート,需要予測', '以下の在庫データから分析レポートを作成してください：'),
        (industry_ids['小売'], 'お客様対応FAQ', 'よくある質問への回答作成', 
         'FAQ,顧客対応,問い合わせ', 'このお客様の問い合わせに対する回答を作成してください：'),
        
        # 飲食業
        (industry_ids['飲食'], 'メニュー開発アイデア', '新メニューのアイデア提案', 
         'メニュー,レシピ,開発,季節', '秋の新メニューのアイデアを5つ提案してください：'),
        (industry_ids['飲食'], 'SNS投稿文作成', '料理写真に添えるSNS投稿文の作成', 
         'SNS,Instagram,投稿,ハッシュタグ', 'この料理写真に合うInstagram投稿文を作成してください：'),
        (industry_ids['飲食'], 'アレルギー対応案内', 'アレルギー情報の説明文作成', 
         'アレルギー,食材,対応,説明', 'メニューのアレルギー情報を分かりやすく説明してください：'),
        
        # 介護業
        (industry_ids['介護'], 'ケアプラン作成支援', '利用者情報からのケアプラン素案作成', 
         'ケアプラン,介護計画,アセスメント', 'この利用者情報からケアプランの素案を作成してください：'),
        (industry_ids['介護'], '家族への報告書作成', '利用者の状況報告書の作成', 
         '報告書,家族,状況報告', '今月の利用者の様子を家族向け報告書にまとめてください：'),
        (industry_ids['介護'], '記録文書の効率化', '介護記録の文章化支援', 
         '記録,文書化,効率化', '以下のメモから正式な介護記録を作成してください：'),
        
        # 医療業
        (industry_ids['医療'], '患者説明資料作成', '患者向け説明資料の作成', 
         '患者説明,資料,分かりやすい', 'この治療法について患者さんに分かりやすく説明してください：'),
        (industry_ids['医療'], '医療文書サマリー', '医療文書の要約作成', 
         '要約,サマリー,カルテ', 'この医療記録の要約を作成してください：'),
        (industry_ids['医療'], '問診票の分析', '問診情報の整理と分析', 
         '問診,分析,症状', '以下の問診情報から重要なポイントを整理してください：'),
        
        # 教育業
        (industry_ids['教育'], '教材作成支援', '授業用教材の作成', 
         '教材,授業,カリキュラム', 'このトピックについて中学生向けの教材を作成してください：'),
        (industry_ids['教育'], 'テスト問題作成', '理解度確認テストの作成', 
         'テスト,問題,評価', 'この単元の理解度を確認するテスト問題を作成してください：'),
        (industry_ids['教育'], '保護者向け通知作成', '保護者への連絡文書作成', 
         '保護者,通知,連絡', '以下の内容を保護者向けにお知らせ文書にしてください：'),
    ]
    
    for ind_id, title, desc, keywords, example in usecases_data:
        cursor.execute('''
        INSERT INTO industry_usecases (industry_id, title, description, keywords, example_prompt)
        VALUES (?, ?, ?, ?, ?)
        ''', (ind_id, title, desc, keywords, example))
    
    print("業種別ユースケースを登録しました")
    
    # ========== サンプル動画を登録 ==========
    # 動画用スラッグセット
    used_video_slugs = set()
    
    def insert_video(title, desc, filename, category_id, uploaded_by):
        """動画を挿入し、自動でスラッグを生成"""
        slug = generate_slug(title, used_video_slugs)
        used_video_slugs.add(slug)
        cursor.execute('''
        INSERT INTO videos (title, slug, description, filename, category_id, uploaded_by)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, slug, desc, filename, category_id, uploaded_by))
        return cursor.lastrowid
    
    sample_video = 'Rakuten AI for Businessのご紹介_1111_20260114_204516.mp4'
    if os.path.exists(sample_video):
        destination = os.path.join('videos', sample_video)
        if not os.path.exists(destination):
            shutil.copy(sample_video, destination)
            print(f"サンプル動画をコピーしました: {sample_video}")
        
        insert_video(
            'Rakuten AI for Businessのご紹介',
            'Rakuten AI for Businessの機能と特徴を紹介する動画です。',
            sample_video,
            prompt_intro_id,
            1
        )
    
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
    parser = argparse.ArgumentParser(description='LMS データベース初期化')
    parser.add_argument('--force', action='store_true', 
                        help='既存データベースを完全にリセット（注意：全データが消えます）')
    parser.add_argument('--migrate', action='store_true',
                        help='差分マイグレーションのみ実行（デフォルト動作）')
    args = parser.parse_args()
    
    if args.force:
        # 強制リセットモード
        print("\n" + "!" * 60)
        print("  警告: --force モードが指定されました")
        print("  既存のデータベースは完全に削除され、再構築されます。")
        print("!" * 60)
        
        # バックアップを作成
        if os.path.exists('lms.db'):
            from migrate_db import create_backup
            backup_path = create_backup()
            if backup_path:
                print(f"  バックアップ: {backup_path}")
        
        confirm = input("\n  本当に実行しますか？ (yes/no): ").strip().lower()
        if confirm == 'yes':
            init_database()
            # マイグレーションバージョンを記録
            from migrate_db import MIGRATIONS, ensure_migration_table, mark_migration
            conn = sqlite3.connect('lms.db')
            cursor = conn.cursor()
            ensure_migration_table(cursor)
            for version, description, _ in MIGRATIONS:
                mark_migration(cursor, version, description)
            conn.commit()
            conn.close()
            print("  マイグレーションバージョンを最新に設定しました")
        else:
            print("  キャンセルしました。データベースは変更されていません。")
    else:
        # デフォルト: 差分マイグレーションモード
        from migrate_db import run_migrations
        run_migrations()
