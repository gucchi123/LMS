# LMS デプロイガイド

このガイドでは、LMSをクラウドサービスにデプロイして公開URLを取得する方法を説明します。

## 🚀 推奨: Render.com でデプロイ（最も簡単）

### ステップ 1: GitHubにコードをプッシュ

```bash
cd "50Development/LMS"

# Gitリポジトリを初期化
git init

# すべてのファイルをステージング
git add .

# コミット
git commit -m "Initial commit: LMS application with industry-based access control"

# GitHubリポジトリを作成後、リモートを追加
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# プッシュ
git push -u origin main
```

### ステップ 2: Render.com でデプロイ

1. **Render.com にサインアップ**
   - https://render.com にアクセス
   - "Get Started for Free" をクリック
   - GitHubアカウントで認証

2. **新しいWebサービスを作成**
   - ダッシュボードで "New +" → "Web Service" をクリック
   - GitHubリポジトリを選択
   - LMSリポジトリを接続

3. **設定を入力**
   ```
   Name: lms-app (または好きな名前)
   Environment: Python
   Build Command: pip install -r requirements.txt
   Start Command: gunicorn app:app
   ```

4. **環境変数を設定**
   - "Environment" タブで以下を追加:
   ```
   SECRET_KEY=your-strong-random-secret-key-here
   FLASK_ENV=production
   ```

5. **デプロイ**
   - "Create Web Service" をクリック
   - 数分でデプロイ完了！
   - URLは `https://lms-app.onrender.com` のような形式

### ステップ 3: データベースを初期化

デプロイ後、Renderのコンソールから:

```bash
python init_db.py
```

これでLMSが公開されました！🎉

---

## 🌐 Option 2: Railway.app でデプロイ

### 手順:

1. **Railway.app にサインアップ**
   - https://railway.app にアクセス
   - GitHubでログイン

2. **新しいプロジェクトを作成**
   - "New Project" → "Deploy from GitHub repo"
   - リポジトリを選択

3. **環境変数を設定**
   - Settings → Variables で追加:
   ```
   SECRET_KEY=your-secret-key
   FLASK_ENV=production
   ```

4. **自動デプロイ**
   - Railwayが自動的に検出してデプロイ
   - URLは `https://your-app.up.railway.app` 形式

---

## ☁️ Option 3: PythonAnywhere でデプロイ

### 手順:

1. **PythonAnywhere にサインアップ**
   - https://www.pythonanywhere.com
   - 無料アカウントを作成

2. **ファイルをアップロード**
   - "Files" タブから手動アップロード
   - または Bash コンソールから `git clone`

3. **Web アプリを設定**
   - "Web" タブ → "Add a new web app"
   - Flask を選択
   - WSGI設定ファイルを編集

4. **URL**
   - `https://yourusername.pythonanywhere.com`

---

## 🐳 Option 4: Fly.io でデプロイ

### 前提条件:
- Dockerfileが必要

### Dockerfile を作成:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python init_db.py

EXPOSE 8080

CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
```

### デプロイ手順:

```bash
# Fly CLI をインストール
# https://fly.io/docs/hands-on/install-flyctl/

# ログイン
fly auth login

# アプリを作成
fly launch

# デプロイ
fly deploy
```

---

## 📋 デプロイ前チェックリスト

- [ ] `.gitignore` に `*.db` と `videos/*` を追加（機密データ保護）
- [ ] `SECRET_KEY` を環境変数で設定
- [ ] `FLASK_ENV=production` を設定
- [ ] `debug=False` を確認
- [ ] `requirements.txt` に `gunicorn` を追加
- [ ] データベース初期化スクリプトを実行
- [ ] デフォルトパスワードを変更

---

## 🔐 セキュリティ設定

### Secret Key の生成:

```python
import secrets
print(secrets.token_hex(32))
```

このキーを環境変数 `SECRET_KEY` に設定してください。

### パスワード変更:

デプロイ後、必ずデフォルトパスワードを変更してください：

**管理者:**
- `admin` / `admin123` → 変更必須

**業種別ユーザー（パスワード: user123）:**
| 業種 | ユーザー名 |
|-----|-----------|
| 宿泊 | `hotel_tanaka`, `ryokan_suzuki` |
| 小売 | `retail_yamada`, `shop_sato` |
| 飲食 | `restaurant_ito` |
| 介護 | `care_watanabe` |
| 医療 | `medical_takahashi` |
| 教育 | `edu_kobayashi` |

---

## 🎬 動画ファイルの扱い

### 注意事項:
- GitHubには大きな動画ファイルをプッシュしない
- 動画は手動でアップロード機能を使用
- または別のストレージサービス（AWS S3, Cloudinary等）を使用

### Git LFS（Large File Storage）を使用する場合:

```bash
# Git LFS をインストール
git lfs install

# 動画ファイルをトラック
git lfs track "*.mp4"

# .gitattributes をコミット
git add .gitattributes
git commit -m "Track video files with Git LFS"
```

---

## 📊 無料枠の比較

| サービス | 無料枠 | 制限 | 自動デプロイ |
|---------|-------|-----|------------|
| **Render** | ✅ あり | 750時間/月、スリープあり | ✅ |
| **Railway** | ✅ $5クレジット | 使用量に応じて消費 | ✅ |
| **PythonAnywhere** | ✅ あり | CPU・メモリ制限あり | ❌ |
| **Fly.io** | ✅ あり | 3つのアプリまで | ✅ |

---

## 🆘 トラブルシューティング

### デプロイが失敗する
- ログを確認
- `requirements.txt` が正しいか確認
- Pythonバージョンを指定（`runtime.txt`）

### データベースが初期化されない
- デプロイ後に手動で `python init_db.py` を実行
- またはデプロイスクリプトに追加

### 動画がアップロードできない
- ファイルサイズ制限を確認
- サーバーの一時ディレクトリの権限を確認
- クラウドストレージの使用を検討

### 業種別アクセスが機能しない
- データベースが正しく初期化されているか確認
- `category_industry_access` テーブルにデータがあるか確認

---

## 🎉 デプロイ成功後

デプロイが成功したら：

1. 公開URLにアクセス
2. `admin / admin123` でログイン
3. パスワードを変更
4. 業種とカテゴリーを設定
5. 動画をアップロード
6. ユーザーを追加（業種・会社名設定）

おめでとうございます！LMSが公開されました！🚀

---

## 📞 サポート

質問や問題がある場合は、開発チームまでご連絡ください。
