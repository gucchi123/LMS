# LMS - Learning Management System

動画ベースの学習管理システム（LMS）です。**マルチテナント**・**業種別アクセス制御**・**ロールベースアクセス制御**を搭載し、各企業・各業種に特化したトレーニングコンテンツを提供できます。

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

## デモ

ローカル環境: http://127.0.0.1:5000

## 機能

### ユーザー機能
- 動画コンテンツの視聴
- 視聴進捗の自動保存・続きから再生
- 視聴完了ステータス
- カテゴリー別・業種別コンテンツ閲覧
- **マイ進捗ダッシュボード**
- **Q&A機能**（質問・回答・編集・削除）
- **社内Q&A**（同テナントのQ&A閲覧）
- **AIチャットアシスタント**（Rakuten AI 3.0連携）
- **お知らせ通知**

### 管理者機能
- 動画のアップロード・編集・削除
- **AI自動文字起こし**（Whisper）
- カテゴリー管理（階層構造）
- **業種管理**
- **カテゴリーアクセス制御**（業種別）
- **テナント（企業）管理**
- **部署管理**（階層構造対応）
- **ユーザー管理**（テナント・部署・ロール設定）
- **CSV一括インポート/エクスポート**
- **動画アナリティクス**
- **ユーザー進捗管理**（テナント別・部署別）
- **Q&A分析ダッシュボード**
- **お知らせ管理**（有効期限・テナント限定配信）
- **GA4トラッキング**

## マルチテナント・ロールベースアクセス制御

| ロール | 説明 |
|--------|------|
| `super_admin` | 全テナント・全機能にアクセス可能 |
| `company_admin` | 自テナント内のユーザー・コンテンツを管理 |
| `user` | 自業種のコンテンツ閲覧・Q&A投稿 |

## 業種別アクセス制御

対応業種（デフォルト）：
- 🏨 宿泊（Accommodation）
- 🏪 小売（Retail）
- 🍽️ 飲食（Food and Beverage）
- 💗 介護（Nursing Care）
- 🏥 医療（Medical Care）
- 🎓 教育（Education）

## クイックスタート（ローカル）

### 1. リポジトリをクローン

```bash
git clone https://github.com/YOUR_USERNAME/LMS.git
cd LMS
```

### 2. パッケージをインストール

```bash
pip install -r requirements.txt
```

### 3. データベースを初期化

```bash
python init_db.py
```

### 4. アプリケーションを起動

```bash
python app.py
```

ブラウザで http://127.0.0.1:5000 にアクセス

## デフォルトアカウント

**管理者:**
- ユーザー名: `admin`
- パスワード: `admin123`
- ロール: `super_admin`

**業種別ユーザー（パスワード: `user123`）:**

| 業種 | ユーザー名 | 会社名 | ロール |
|-----|-----------|-------|--------|
| 🏨 宿泊 | `hotel_tanaka` | グランドホテル東京 | `company_admin` |
| 🏨 宿泊 | `ryokan_suzuki` | 湯元旅館 | `user` |
| 🏪 小売 | `retail_yamada` | スーパーマート | `company_admin` |
| 🏪 小売 | `shop_sato` | ファッションストア | `user` |
| 🍽️ 飲食 | `restaurant_ito` | さくらレストラン | `user` |
| 💗 介護 | `care_watanabe` | スマイルケアセンター | `user` |
| 🏥 医療 | `medical_takahashi` | セントラルクリニック | `user` |
| 🎓 教育 | `edu_kobayashi` | ブライトアカデミー | `user` |

> **重要**: 本番環境では必ずパスワードを変更してください

## デプロイ（公開URLの取得）

詳細は [DEPLOYMENT.md](DEPLOYMENT.md) を参照してください。

### Render.com にデプロイ（推奨）

1. GitHubにコードをプッシュ
2. [Render.com](https://render.com) でアカウント作成
3. GitHubリポジトリを接続
4. 環境変数を設定:
   - `SECRET_KEY`: 強力なランダム文字列
   - `FLASK_ENV`: `production`
5. デプロイ完了！

公開URL: `https://your-app-name.onrender.com`

### その他のデプロイオプション

- **PythonAnywhere**: Python専用ホスティング（[詳細ガイド](DEPLOY_PYTHONANYWHERE.md)）
- **Railway.app**: 簡単デプロイ、$5/月の無料クレジット
- **Fly.io**: Docker対応、高パフォーマンス
- **Cloudflare Tunnel**: ローカルサーバーの外部公開（[セットアップガイド](CLOUDFLARE_TUNNEL_SETUP.md)）

## プロジェクト構造

```
LMS/
├── app.py                  # メインアプリケーション
├── init_db.py              # データベース初期化
├── migrate_db.py           # 差分マイグレーション
├── test_app.py             # テストスイート（198テスト）
├── requirements.txt        # 依存パッケージ
├── Procfile                # デプロイ設定
├── runtime.txt             # Pythonバージョン
├── .gitignore              # Git除外設定
├── README.md               # 詳細ドキュメント
├── QUICKSTART.md           # 使い方ガイド
├── DEPLOYMENT.md           # デプロイガイド
├── lms.db                  # SQLiteデータベース
├── videos/                 # 動画保存フォルダ
├── db_backups/             # DBバックアップ
└── templates/              # HTMLテンプレート（14ファイル）
    ├── login.html          # ログインページ
    ├── course_catalog.html # コースカタログ
    ├── category_detail.html # カテゴリー詳細
    ├── dashboard.html      # ダッシュボード
    ├── watch.html          # 動画視聴（Q&A含む）
    ├── admin.html          # 管理画面
    ├── chat.html           # AIチャット
    ├── chat_widget.html    # チャットウィジェット
    ├── my_progress.html    # マイ進捗（社内Q&A含む）
    ├── analytics.html      # アクセスアナリティクス
    ├── video_analytics.html # 動画アナリティクス
    ├── user_progress.html  # ユーザー進捗管理
    ├── qa_analytics.html   # Q&A分析
    └── ga4_tracking.html   # GA4トラッキング
```

## 技術スタック

- **Backend**: Flask 3.0.0
- **Database**: SQLite
- **Frontend**: Bootstrap 5 + Video.js
- **Authentication**: Flask Sessions + Werkzeug
- **AI**: Rakuten AI 3.0 API + OpenAI Whisper
- **Analytics**: Google Analytics 4
- **Deployment**: Gunicorn

## ドキュメント

- [QUICKSTART.md](QUICKSTART.md) - 使い始め方
- [DEPLOYMENT.md](DEPLOYMENT.md) - デプロイ手順
- [DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md) - PythonAnywhereデプロイ
- [CLOUDFLARE_TUNNEL_SETUP.md](CLOUDFLARE_TUNNEL_SETUP.md) - Cloudflare Tunnel
- [TRANSCRIPTION_GUIDE.md](TRANSCRIPTION_GUIDE.md) - 文字起こし機能
- [README.md](README.md) - 技術仕様（詳細版）

## セキュリティ

本番環境で使用する場合は以下を実施してください：

1. SECRET_KEYを環境変数で設定
2. デフォルトパスワードを変更
3. HTTPSを使用
4. `FLASK_ENV=production` を設定
5. データベースのバックアップ

### Secret Key の生成

```python
import secrets
print(secrets.token_hex(32))
```

## テスト

```bash
# pytestをインストール
pip install pytest

# テストを実行
python -m pytest test_app.py -v
```

全198テストが含まれています：
- ログイン・認証テスト
- ロールベースアクセス制御テスト
- 業種別アクセス制御テスト
- テナント・部署管理テスト
- CSV インポート/エクスポートテスト
- セキュリティバリデーションテスト
- 動画アナリティクステスト
- ユーザー進捗テスト
- Q&A機能テスト（社内Q&A含む）
- Q&A分析テスト
- お知らせ機能テスト
- GA4統合テスト
- データベースマイグレーションテスト

## データベーススキーマ

### テーブル一覧（18テーブル）

| テーブル | 説明 |
|---------|------|
| `users` | ユーザー情報（業種・テナント・部署・ロール含む） |
| `industries` | 業種マスタ |
| `tenants` | テナント（企業） |
| `departments` | 部署（階層構造対応） |
| `categories` | カテゴリー（階層構造対応） |
| `category_industry_access` | アクセス制御 |
| `videos` | 動画情報（スラッグ・文字起こしステータス含む） |
| `video_transcripts` | 文字起こしテキスト |
| `video_questions` | Q&A質問 |
| `video_answers` | Q&A回答 |
| `progress` | 視聴進捗 |
| `announcements` | お知らせ・通知 |
| `chat_history` | チャット履歴 |
| `external_knowledge` | 外部ナレッジ（RAG用） |
| `industry_usecases` | 業種別ユースケース |
| `access_logs` | アクセスログ |
| `schema_migrations` | マイグレーション管理 |

## 動画のアップロード

- サポート形式: MP4, AVI, MOV, MKV, WebM
- 最大サイズ: 500MB
- 推奨: MP4（H.264コーデック）

## トラブルシューティング

### サーバーが起動しない
```bash
# パッケージを再インストール
pip install -r requirements.txt
```

### データベースエラー
```bash
# データベースを再初期化
python init_db.py
```

### 動画が再生されない
- ブラウザのコンソール（F12）でエラーを確認
- MP4形式を使用することを推奨

### カテゴリーが表示されない
- ログインユーザーの業種を確認
- 管理画面でアクセス制御設定を確認

## ライセンス

このプロジェクトは社内利用を想定しています。

## サポート

問題や質問がある場合は、Issueを作成するか開発チームまでご連絡ください。

---

**Built with Flask**
