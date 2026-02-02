# LMS - Learning Management System

動画ベースの学習管理システム（LMS）です。**業種別アクセス制御**機能を搭載し、各業種に特化したトレーニングコンテンツを提供できます。

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

## 📺 デモ

ローカル環境: http://127.0.0.1:5000

## ✨ 機能

### ユーザー機能
- 📹 動画コンテンツの視聴
- 📊 視聴進捗の自動保存
- ▶️ 前回の続きから再生
- 🎯 視聴完了ステータス
- 📂 カテゴリー別コンテンツ閲覧
- 🏢 **業種別コンテンツアクセス**

### 管理者機能
- 📤 動画のアップロード
- ✏️ 動画情報の編集
- 🗑️ 動画の削除
- 📁 カテゴリー管理（階層構造）
- 🏭 **業種管理**
- 🔐 **カテゴリーアクセス制御**
- 👥 ユーザー管理
- 📈 視聴統計の閲覧

## 🏢 業種別アクセス制御

このLMSの特徴は、**業種別にコンテンツへのアクセスを制御**できることです。

### 対応業種（デフォルト）
- 🏨 宿泊（Accommodation）
- 🏪 小売（Retail）
- 🍽️ 飲食（Food and Beverage）
- 💗 介護（Nursing Care）
- 🏥 医療（Medical Care）
- 🎓 教育（Education）

## 🚀 クイックスタート（ローカル）

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

## 🔑 デフォルトアカウント

**管理者:**
- ユーザー名: `admin`
- パスワード: `admin123`

**業種別ユーザー（パスワード: `user123`）:**

| 業種 | ユーザー名 | 会社名 |
|-----|-----------|-------|
| 🏨 宿泊 | `hotel_tanaka` | グランドホテル東京 |
| 🏨 宿泊 | `ryokan_suzuki` | 湯元旅館 |
| 🏪 小売 | `retail_yamada` | スーパーマート |
| 🏪 小売 | `shop_sato` | ファッションストア |
| 🍽️ 飲食 | `restaurant_ito` | さくらレストラン |
| 💗 介護 | `care_watanabe` | スマイルケアセンター |
| 🏥 医療 | `medical_takahashi` | セントラルクリニック |
| 🎓 教育 | `edu_kobayashi` | ブライトアカデミー |

> ⚠️ **重要**: 本番環境では必ずパスワードを変更してください

## 🌐 デプロイ（公開URLの取得）

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

- **Railway.app**: 簡単デプロイ、$5/月の無料クレジット
- **PythonAnywhere**: Python専用ホスティング
- **Fly.io**: Docker対応、高パフォーマンス

## 📁 プロジェクト構造

```
LMS/
├── app.py                  # メインアプリケーション
├── init_db.py              # データベース初期化
├── test_app.py             # テストスイート（29テスト）
├── requirements.txt        # 依存パッケージ
├── Procfile                # デプロイ設定
├── runtime.txt             # Pythonバージョン
├── .gitignore              # Git除外設定
├── README.md               # 詳細ドキュメント
├── QUICKSTART.md           # 使い方ガイド
├── DEPLOYMENT.md           # デプロイガイド
├── lms.db                  # SQLiteデータベース
├── videos/                 # 動画保存フォルダ
└── templates/              # HTMLテンプレート
    ├── login.html          # ログインページ
    ├── course_catalog.html # コースカタログ
    ├── category_detail.html # カテゴリー詳細
    ├── dashboard.html      # ダッシュボード
    ├── watch.html          # 動画視聴
    └── admin.html          # 管理画面
```

## 🛠️ 技術スタック

- **Backend**: Flask 3.0.0
- **Database**: SQLite
- **Frontend**: Bootstrap 5 + Video.js
- **Authentication**: Flask Sessions + Werkzeug
- **Deployment**: Gunicorn

## 📖 ドキュメント

- [QUICKSTART.md](QUICKSTART.md) - 使い始め方
- [DEPLOYMENT.md](DEPLOYMENT.md) - デプロイ手順
- [README.md](README.md) - 技術仕様（詳細版）

## 🔐 セキュリティ

本番環境で使用する場合は以下を実施してください：

1. ✅ SECRET_KEYを環境変数で設定
2. ✅ デフォルトパスワードを変更
3. ✅ HTTPSを使用
4. ✅ debug=Falseを確認
5. ✅ データベースのバックアップ

### Secret Key の生成

```python
import secrets
print(secrets.token_hex(32))
```

## 🧪 テスト

```bash
# pytestをインストール
pip install pytest

# テストを実行
python -m pytest test_app.py -v
```

全29テストが含まれています：
- ログイン機能テスト
- 業種別アクセス制御テスト
- 管理画面アクセステスト
- API テスト

## 🎬 動画のアップロード

- サポート形式: MP4, AVI, MOV, MKV, WebM
- 最大サイズ: 500MB
- 推奨: MP4（H.264コーデック）

## 🆘 トラブルシューティング

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

## 📊 データベーススキーマ

### テーブル一覧
| テーブル | 説明 |
|---------|------|
| `users` | ユーザー情報（業種・会社名含む） |
| `industries` | 業種マスタ |
| `categories` | カテゴリー（階層構造対応） |
| `category_industry_access` | アクセス制御 |
| `videos` | 動画情報 |
| `progress` | 視聴進捗 |

## 🤝 コントリビューション

プルリクエストを歓迎します！以下の手順で：

1. リポジトリをフォーク
2. フィーチャーブランチを作成 (`git checkout -b feature/AmazingFeature`)
3. 変更をコミット (`git commit -m 'Add some AmazingFeature'`)
4. ブランチにプッシュ (`git push origin feature/AmazingFeature`)
5. プルリクエストを作成

## 📄 ライセンス

このプロジェクトは社内利用を想定しています。

## 📞 サポート

問題や質問がある場合は、Issueを作成するか開発チームまでご連絡ください。

---

**Built with ❤️ using Flask**
