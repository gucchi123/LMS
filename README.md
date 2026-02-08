# Learning Management System (LMS)

動画ベースの学習管理システムです。**業種別アクセス制御**・**マルチテナント**・**ロールベースアクセス制御**を搭載し、各業種・各企業に特化したトレーニングコンテンツを提供できます。

## 機能

### ユーザー機能
- ログイン/ログアウト認証
- 動画コンテンツの視聴
- 視聴進捗の自動保存（5秒ごと）
- 前回の続きから再生
- 視聴完了ステータス表示
- カテゴリー別コンテンツ閲覧
- **業種別コンテンツアクセス**
- **マイ進捗ダッシュボード**（視聴率・完了状況・モチベーション表示）
- **Q&A機能**（動画ごとの質問・回答、編集・削除）
- **社内Q&A**（同テナントのメンバーのQ&Aを閲覧）
- **AIチャットアシスタント**（Rakuten AI 3.0連携、RAG検索）
- **お知らせ通知**（全体通知・テナント別通知）

### 管理者機能
- 動画のアップロード（MP4, AVI, MOV, MKV, WebM対応）
- 動画情報の編集・削除
- **AI自動文字起こし**（Whisper使用）
- 動画トランスクリプトと概要の自動生成
- カテゴリー管理（階層構造対応）
- **業種管理**（追加・編集・削除）
- **カテゴリーアクセス制御**（業種別に公開設定）
- **テナント（企業）管理**
- **部署管理**（テナント別、階層構造対応）
- **ユーザー管理**（業種・会社名・テナント・部署・ロール設定）
- **CSV一括インポート/エクスポート**
- **動画アナリティクス**（視聴統計・テナント別分析）
- **ユーザー進捗管理**（テナント別・部署別）
- **Q&A分析ダッシュボード**（未回答質問・回答率・テナント別統計）
- **お知らせ管理**（作成・編集・有効期限・テナント限定配信）
- **GA4トラッキング**

## マルチテナント・ロールベースアクセス制御

### ロール

| ロール | 説明 | 権限 |
|--------|------|------|
| `super_admin` | システム全体管理者 | 全テナント・全機能にアクセス可能 |
| `company_admin` | 企業管理者 | 自テナント内のユーザー・コンテンツを管理 |
| `user` | 一般ユーザー | 自業種のコンテンツ閲覧・Q&A投稿 |

### テナント分離
- 各企業（テナント）のデータは完全に分離
- `company_admin` は自テナントのユーザー・統計のみ閲覧可能
- Q&Aもテナント境界で分離（社内Q&Aは同テナント内のみ）
- お知らせはテナント限定配信が可能

## 業種別アクセス制御

### 対応業種（デフォルト）
| 業種 | 英語名 | アイコン |
|-----|-------|---------|
| 宿泊 | Accommodation | 🏨 |
| 小売 | Retail | 🏪 |
| 飲食 | Food and Beverage | 🍽️ |
| 介護 | Nursing Care | 💗 |
| 医療 | Medical Care | 🏥 |
| 教育 | Education | 🎓 |

### アクセス制御の仕組み
- **全業種公開**: アクセス制限なし（全ユーザーが閲覧可能）
- **業種限定**: 指定した業種のユーザーのみ閲覧可能
- **管理者**: すべてのカテゴリーにアクセス可能

## 技術スタック

- **Backend**: Flask (Python)
- **Frontend**: HTML/CSS/JavaScript + Bootstrap 5
- **Database**: SQLite
- **Video Player**: Video.js
- **Authentication**: Flask Sessions + Werkzeug Security
- **AI**: Rakuten AI 3.0 API（チャット・概要生成）、OpenAI Whisper（文字起こし）
- **Analytics**: Google Analytics 4 (GA4)
- **日本語処理**: pykakasi（ローマ字変換・スラッグ生成）

## セットアップ方法

### 1. 必要なパッケージをインストール

```bash
pip install -r requirements.txt
```

### 2. データベースを初期化

```bash
python init_db.py
```

これにより以下が作成されます：
- データベースファイル (`lms.db`)
- ビデオ保存フォルダ (`videos/`)
- 業種マスタデータ
- テナント・部署データ
- サンプルユーザーアカウント（ロール付き）
- サンプルカテゴリー（業種別アクセス制御付き）

### 3. アプリケーションを起動

```bash
python app.py
```

ブラウザで http://localhost:5000 にアクセスします。

### 4. 環境変数（オプション）

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `SECRET_KEY` | セッション暗号化キー | 開発用デフォルト値 |
| `FLASK_ENV` | 実行環境 | `development` |
| `RAKUTEN_AI_API_KEY` | Rakuten AI 3.0 APIキー | 空（チャット無効） |
| `RAKUTEN_AI_BASE_URL` | APIエンドポイント | Rakuten AI公開URL |
| `RAKUTEN_AI_MODEL` | 使用モデル名 | `rakutenai-3.0` |
| `GA_MEASUREMENT_ID` | GA4 Measurement ID | 空（トラッキング無効） |
| `LMS_DATABASE` | データベースファイルパス | `lms.db` |
| `PORT` | ポート番号 | `5000` |

### 5. 文字起こし機能を使用する場合（オプション）

文字起こし機能を使用するには**ffmpeg**が必要です：

#### 方法1: ローカルにffmpegを配置（推奨）
既に`ffmpeg.exe`がLMSフォルダに配置されていれば、自動的に使用されます。

#### 方法2: システム全体にインストール
Chocolateyを使用:
```powershell
choco install ffmpeg
```

**文字起こしのテスト:**
```bash
python test_whisper.py
```

**失敗したステータスをリセット:**
```bash
python reset_status.py
```

## デフォルトアカウント

初期化後、以下のアカウントが利用可能です：

### 管理者アカウント
- **ユーザー名**: `admin`
- **パスワード**: `admin123`
- **ロール**: `super_admin`
- **権限**: 全テナント・全カテゴリーアクセス、全管理機能

### 業種別ユーザーアカウント（パスワードは全て `user123`）

| 業種 | ユーザー名 | 会社名 | ロール |
|-----|-----------|-------|--------|
| 宿泊 | `hotel_tanaka` | グランドホテル東京 | `company_admin` |
| 宿泊 | `ryokan_suzuki` | 湯元旅館 | `user` |
| 小売 | `retail_yamada` | スーパーマート | `company_admin` |
| 小売 | `shop_sato` | ファッションストア | `user` |
| 飲食 | `restaurant_ito` | さくらレストラン | `user` |
| 介護 | `care_watanabe` | スマイルケアセンター | `user` |
| 医療 | `medical_takahashi` | セントラルクリニック | `user` |
| 教育 | `edu_kobayashi` | ブライトアカデミー | `user` |

## カテゴリー構造とアクセス権

```
├── 基礎編              [全業種公開]
│   ├── プロンプト入門
│   └── 基本操作ガイド
├── 応用編              [全業種公開]
│   ├── 業務活用術
│   └── データ分析活用
├── 実践編              [全業種公開]
│   ├── 事例紹介
│   └── ワークショップ
├── 宿泊業向けAI活用    [宿泊業のみ]
│   ├── 予約管理の効率化
│   └── 多言語対応
├── 小売業向けAI活用    [小売業のみ]
│   └── 在庫管理の最適化
├── 飲食業向けAI活用    [飲食業のみ]
│   └── メニュー開発支援
├── 介護業向けAI活用    [介護業のみ]
│   └── ケアプラン作成支援
├── 医療業向けAI活用    [医療業のみ]
│   └── 医療文書作成支援
└── 教育業向けAI活用    [教育業のみ]
    └── 教材作成支援
```

## ディレクトリ構造

```
50Development/LMS/
├── app.py                          # メインアプリケーション
├── init_db.py                      # データベース初期化スクリプト
├── migrate_db.py                   # 差分マイグレーションスクリプト
├── test_app.py                     # テストスイート（198テスト）
├── test_whisper.py                 # Whisper文字起こしテスト
├── reset_status.py                 # 文字起こしステータスリセット
├── add_external_knowledge.py       # 外部ナレッジ追加スクリプト
├── requirements.txt                # 依存パッケージ
├── ffmpeg.exe                      # 文字起こし用（オプション）
├── README.md                       # このファイル
├── QUICKSTART.md                   # クイックスタートガイド
├── DEPLOYMENT.md                   # デプロイガイド
├── DEPLOY_PYTHONANYWHERE.md        # PythonAnywhereデプロイガイド
├── CLOUDFLARE_TUNNEL_SETUP.md      # Cloudflare Tunnelセットアップガイド
├── TRANSCRIPTION_GUIDE.md          # 文字起こし機能ガイド
├── start_production.ps1            # 本番起動スクリプト
├── run_tunnel.ps1                  # トンネル起動スクリプト
├── lms.db                          # SQLiteデータベース（自動生成）
├── videos/                         # 動画ファイル保存先（自動生成）
│   └── *.mp4
├── db_backups/                     # データベースバックアップ（自動生成）
└── templates/                      # HTMLテンプレート
    ├── login.html                  # ログインページ
    ├── course_catalog.html         # コースカタログ（カテゴリー一覧）
    ├── category_detail.html        # カテゴリー詳細ページ
    ├── dashboard.html              # ユーザーダッシュボード
    ├── watch.html                  # 動画視聴ページ（Q&A含む）
    ├── admin.html                  # 管理者ダッシュボード
    ├── chat.html                   # AIチャットページ
    ├── chat_widget.html            # チャットウィジェット（埋め込み用）
    ├── my_progress.html            # マイ進捗ダッシュボード（社内Q&A含む）
    ├── analytics.html              # アクセスアナリティクス
    ├── video_analytics.html        # 動画アナリティクス
    ├── user_progress.html          # ユーザー進捗管理（管理者用）
    ├── qa_analytics.html           # Q&A分析ダッシュボード
    └── ga4_tracking.html           # GA4トラッキングコード
```

## データベーススキーマ

### industries テーブル（業種マスタ）
- `id`: 業種ID（主キー）
- `name`: 業種名（日本語）
- `name_en`: 業種名（英語）
- `description`: 説明
- `icon`: アイコンクラス
- `color`: カラーコード
- `created_at`: 作成日時

### tenants テーブル（テナント/企業）
- `id`: テナントID（主キー）
- `name`: テナント名
- `industry_id`: 業種ID（外部キー）
- `logo`: ロゴ
- `settings`: 設定（JSON）
- `created_at`: 作成日時

### departments テーブル（部署）
- `id`: 部署ID（主キー）
- `tenant_id`: テナントID（外部キー）
- `name`: 部署名
- `parent_department_id`: 親部署ID（階層構造用）
- `created_at`: 作成日時

### users テーブル
- `id`: ユーザーID（主キー）
- `username`: ユーザー名（ユニーク）
- `email`: メールアドレス（ユニーク）
- `password_hash`: ハッシュ化されたパスワード
- `industry_id`: 所属業種ID（外部キー）
- `company_name`: 会社名
- `is_admin`: 管理者フラグ（レガシー、`role`で管理）
- `tenant_id`: テナントID（外部キー）
- `department_id`: 部署ID（外部キー）
- `role`: ロール（`super_admin` / `company_admin` / `user`）
- `created_at`: 登録日時

### categories テーブル
- `id`: カテゴリーID（主キー）
- `name`: カテゴリー名
- `description`: 説明
- `icon`: アイコンクラス
- `color`: カラーコード
- `parent_id`: 親カテゴリーID（外部キー、階層構造用）
- `display_order`: 表示順
- `created_at`: 作成日時

### category_industry_access テーブル（アクセス制御）
- `id`: ID（主キー）
- `category_id`: カテゴリーID（外部キー）
- `industry_id`: 業種ID（外部キー）
- `created_at`: 作成日時

> ※レコードがないカテゴリーは「全業種公開」

### videos テーブル
- `id`: 動画ID（主キー）
- `title`: 動画タイトル
- `slug`: URLスラッグ（自動生成）
- `description`: 説明
- `filename`: ファイル名
- `category_id`: カテゴリーID（外部キー）
- `uploaded_by`: アップロードしたユーザーID
- `transcription_status`: 文字起こしステータス（`none` / `pending` / `processing` / `completed` / `failed`）
- `summary`: AI生成の概要文
- `created_at`: アップロード日時

### video_transcripts テーブル（文字起こし）
- `id`: ID（主キー）
- `video_id`: 動画ID（外部キー）
- `content`: 文字起こしテキスト
- `content_type`: コンテンツ種別（`transcript` / `description`）
- `timestamp_start`: 開始タイムスタンプ
- `timestamp_end`: 終了タイムスタンプ
- `created_at`: 作成日時

### video_questions テーブル（Q&A質問）
- `id`: 質問ID（主キー）
- `video_id`: 動画ID（外部キー）
- `user_id`: 投稿ユーザーID（外部キー）
- `tenant_id`: テナントID（外部キー）
- `question_text`: 質問テキスト
- `created_at`: 作成日時
- `updated_at`: 更新日時

### video_answers テーブル（Q&A回答）
- `id`: 回答ID（主キー）
- `question_id`: 質問ID（外部キー）
- `user_id`: 回答ユーザーID（外部キー）
- `answer_text`: 回答テキスト
- `is_admin_answer`: 管理者回答フラグ
- `created_at`: 作成日時
- `updated_at`: 更新日時

### announcements テーブル（お知らせ）
- `id`: ID（主キー）
- `author_id`: 作成者ユーザーID（外部キー）
- `title`: タイトル
- `content`: 本文
- `type`: 種別（`info` / `warning` / `important`）
- `target_tenant_id`: 対象テナントID（NULLは全体通知）
- `is_active`: 有効フラグ
- `publish_at`: 公開日時
- `expires_at`: 有効期限
- `created_at`: 作成日時

### chat_history テーブル（チャット履歴）
- `id`: ID（主キー）
- `user_id`: ユーザーID（外部キー）
- `message`: ユーザーメッセージ
- `response`: AI応答
- `recommended_videos`: 推薦動画ID（JSON）
- `created_at`: 作成日時

### external_knowledge テーブル（外部ナレッジ）
- `id`: ID（主キー）
- `industry_id`: 業種ID（外部キー）
- `title`: タイトル
- `content`: コンテンツ
- `source_file`: ソースファイル
- `section`: セクション
- `keywords`: キーワード
- `created_at`: 作成日時
- `updated_at`: 更新日時

### progress テーブル
- `id`: 進捗ID（主キー）
- `user_id`: ユーザーID（外部キー）
- `video_id`: 動画ID（外部キー）
- `progress_percent`: 視聴進捗率（0-100）
- `last_position`: 最後の再生位置（秒）
- `updated_at`: 更新日時

### industry_usecases テーブル（業種別ユースケース）
- `id`: ID（主キー）
- `industry_id`: 業種ID（外部キー）
- `title`: ユースケースタイトル
- `description`: 説明

### schema_migrations テーブル（マイグレーション管理）
- `version`: マイグレーションバージョン
- `description`: 説明
- `applied_at`: 適用日時

### access_logs テーブル（アクセスログ）
- `id`: ID（主キー）
- `user_id`: ユーザーID
- `tenant_id`: テナントID
- `path`: アクセスパス
- `method`: HTTPメソッド
- `status_code`: ステータスコード
- `user_agent`: ユーザーエージェント
- `ip_address`: IPアドレス
- `referrer`: リファラー
- `duration_ms`: 処理時間（ミリ秒）
- `extra`: 追加情報
- `created_at`: 作成日時

## データベースマイグレーション

起動時に自動で差分マイグレーションが実行されます（`migrate_db.py`）。
手動でのDB初期化が不要な場合でも、テーブル追加・カラム追加は自動適用されます。

```bash
# 初回のみ: フルDB初期化
python init_db.py

# 以降はアプリ起動時に自動マイグレーション
python app.py
```

## テストの実行

```bash
# pytestをインストール
pip install pytest

# テストを実行
python -m pytest test_app.py -v
```

全198テストが含まれています：
- ログイン機能テスト
- 業種別アクセス制御テスト
- 管理画面アクセステスト
- 業種管理APIテスト
- カテゴリー管理APIテスト
- ユーザー管理APIテスト
- テナント管理APIテスト
- 部署管理APIテスト
- CSV インポート/エクスポートテスト
- セキュリティバリデーションテスト
- ロールベースアクセス制御テスト
- GA4統合テスト
- データベースマイグレーションテスト
- 動画アナリティクステスト
- ユーザー進捗テスト
- マイ進捗テスト
- テナント管理者保護テスト
- Q&A機能テスト（投稿・編集・削除・権限制御）
- Q&A分析ダッシュボードテスト
- マイQ&A・社内Q&Aテスト
- お知らせ機能テスト

## 使い方

### ユーザー向け

1. **ログイン**
   - ユーザー名とパスワードを入力してログイン
   - 業種に応じたコンテンツが表示されます

2. **コースを選択**
   - コースカタログからカテゴリーを選択
   - 自分の業種に対応したカテゴリーのみ表示されます

3. **動画を視聴**
   - カテゴリー内の動画を選択して視聴開始
   - 進捗は自動的に保存されます（5秒ごと）

4. **視聴を再開**
   - 前回視聴した動画は続きから再生されます
   - 進捗バーで視聴状況を確認できます

5. **マイ進捗を確認**
   - マイ進捗ページで全体の視聴進捗を確認
   - カテゴリー別・動画別の進捗率を表示

6. **Q&Aで質問・回答**
   - 動画視聴ページのQ&Aタブから質問を投稿
   - 他のメンバーの質問に回答可能
   - 社内Q&Aタブで同じ会社のQ&Aを閲覧

7. **AIチャット**
   - チャットページで業務に関する質問を投稿
   - Rakuten AI 3.0が業種に応じた回答を生成
   - 関連する動画コンテンツも推薦

### 管理者向け

1. **管理画面にアクセス**
   - 管理者アカウントでログイン
   - 自動的に管理画面へ遷移

2. **動画をアップロード**
   - 「新しい動画をアップロード」ボタンをクリック
   - タイトル、説明、カテゴリー、動画ファイルを選択
   - アップロードを実行

3. **カテゴリーを管理**
   - カテゴリーの追加・編集・削除
   - サブカテゴリーの作成
   - アイコンとカラーのカスタマイズ

4. **アクセス制御を設定**
   - カテゴリーの🔐ボタンをクリック
   - アクセスを許可する業種を選択
   - 業種を選択しない場合は「全業種公開」

5. **業種を管理**
   - 新しい業種の追加
   - 業種情報の編集
   - 不要な業種の削除

6. **ユーザーを管理**
   - 新しいユーザーの作成（業種・会社名・テナント・部署・ロール設定）
   - ユーザー情報の編集
   - CSV一括インポート/エクスポート

7. **アナリティクスを確認**
   - 動画アナリティクス: 動画ごとの視聴統計
   - ユーザー進捗: テナント別・部署別の進捗状況
   - Q&A分析: 質問数・回答率・未回答質問一覧

8. **お知らせを管理**
   - お知らせの作成（全体通知またはテナント限定）
   - 有効期限の設定
   - 有効/無効の切り替え

## セキュリティに関する注意

- **本番環境では必ず以下を変更してください**:
  - 環境変数 `SECRET_KEY` を強力なランダム文字列に設定
  - デフォルトアカウントのパスワードを変更
  - HTTPS を使用する
  - 環境変数 `FLASK_ENV=production` を設定

## トラブルシューティング

### 動画が再生されない
- ブラウザが動画形式をサポートしているか確認
- MP4形式（H.264コーデック）が最も互換性が高い

### 進捗が保存されない
- ブラウザのコンソールでエラーを確認
- データベースファイルの書き込み権限を確認

### アップロードが失敗する
- ファイルサイズが500MBを超えていないか確認
- `videos/` フォルダの書き込み権限を確認

### カテゴリーが表示されない
- ログインユーザーの業種とカテゴリーのアクセス設定を確認
- 管理画面でアクセス制御設定を確認

### 文字起こしが失敗する
- **原因**: ffmpegがインストールされていない、またはPATHが通っていない
- **解決策1**: LMSフォルダに`ffmpeg.exe`を配置（推奨）
- **解決策2**: システム全体にffmpegをインストール（`choco install ffmpeg`）
- **テスト**: `python test_whisper.py`を実行してffmpegが正常に動作するか確認
- **リセット**: `python reset_status.py`で失敗ステータスをリセット

## カスタマイズ

### 最大ファイルサイズの変更
`app.py` の以下の行を変更：
```python
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
```

### 進捗保存の間隔変更
`templates/watch.html` の以下の行を変更：
```javascript
progressSaveInterval = setInterval(saveProgress, 5000);  // 5000ms = 5秒
```

## ライセンス

このプロジェクトは社内利用を想定しています。

## サポート

問題が発生した場合は、開発チームまでお問い合わせください。
