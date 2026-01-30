# 🚀 GitHubにデプロイして公開URLを取得する方法

このガイドでは、LMSをGitHubにプッシュし、Render.comで公開URLを取得する手順を説明します。

---

## 📋 前提条件

- [ ] GitHubアカウント
- [ ] Git がインストールされている
- [ ] LMSが正常に動作している（ローカルでテスト済み）

---

## ステップ1️⃣: GitHubリポジトリを作成

### 1.1 GitHubにログイン
https://github.com にアクセスしてログイン

### 1.2 新しいリポジトリを作成
1. 右上の「+」→「New repository」をクリック
2. 以下の情報を入力：
   - **Repository name**: `LMS` (または好きな名前)
   - **Description**: `Learning Management System - Video-based training platform`
   - **Public** or **Private**: お好みで選択
   - **Initialize this repository with:** すべてチェックなし
3. 「Create repository」をクリック

### 1.3 リポジトリURLをコピー
作成されたリポジトリのURLをコピー（例: `https://github.com/your-username/LMS.git`）

---

## ステップ2️⃣: ローカルからGitHubにプッシュ

### 2.1 PowerShellまたはコマンドプロンプトを開く

```powershell
cd "C:\Users\makoto.mizuguchi\OneDrive - Rakuten Group, Inc\CursorFiles\50Development\LMS"
```

### 2.2 Gitリポジトリを初期化

```bash
git init
```

### 2.3 ファイルをステージング

```bash
git add .
```

### 2.4 最初のコミット

```bash
git commit -m "Initial commit: Learning Management System"
```

### 2.5 リモートリポジトリを追加

```bash
# YOUR_USERNAMEとYOUR_REPO_NAMEを実際の値に置き換える
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
```

例:
```bash
git remote add origin https://github.com/makoto-mizuguchi/LMS.git
```

### 2.6 メインブランチにプッシュ

```bash
# ブランチ名をmainに変更（必要な場合）
git branch -M main

# GitHubにプッシュ
git push -u origin main
```

> ⚠️ **認証エラーが出た場合**
> - GitHubの Personal Access Token が必要です
> - Settings → Developer settings → Personal access tokens → Generate new token
> - パスワードの代わりにトークンを使用

---

## ステップ3️⃣: Render.com でデプロイ

### 3.1 Render.com にサインアップ

1. https://render.com にアクセス
2. 「Get Started for Free」をクリック
3. 「Sign in with GitHub」を選択
4. GitHubアカウントで認証

### 3.2 新しいWebサービスを作成

1. ダッシュボードで「New +」をクリック
2. 「Web Service」を選択
3. 「Connect a repository」セクションで：
   - 「Configure account」をクリック（初回のみ）
   - Render がアクセスできるリポジトリを選択
   - 作成したLMSリポジトリを選択
4. 「Connect」をクリック

### 3.3 サービスの設定

以下の情報を入力：

| 項目 | 値 |
|-----|-----|
| **Name** | `lms-app` (または好きな名前) |
| **Region** | `Singapore` (日本に近い) |
| **Branch** | `main` |
| **Root Directory** | (空白のまま) |
| **Environment** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app` |
| **Instance Type** | `Free` |

### 3.4 環境変数を設定

「Advanced」をクリックして展開し、以下の環境変数を追加：

#### 必須の環境変数:

1. **SECRET_KEY**
   ```
   Key: SECRET_KEY
   Value: [強力なランダム文字列を生成して貼り付け]
   ```
   
   Secret Keyの生成方法（Pythonで実行）:
   ```python
   import secrets
   print(secrets.token_hex(32))
   ```

2. **FLASK_ENV**
   ```
   Key: FLASK_ENV
   Value: production
   ```

### 3.5 デプロイを開始

1. 「Create Web Service」をクリック
2. デプロイが開始されます（数分かかります）
3. ログを確認しながら待ちます

### 3.6 データベースを初期化

デプロイが完了したら、Renderのシェルでデータベースを初期化：

1. Renderダッシュボードでサービスを開く
2. 「Shell」タブをクリック
3. 以下のコマンドを実行：
   ```bash
   python init_db.py
   ```

---

## ステップ4️⃣: 公開URLにアクセス

### 4.1 URLを確認

Renderダッシュボードの上部に表示されているURLをクリック：

```
https://lms-app.onrender.com
```

（実際のURLはサービス名によって異なります）

### 4.2 初回ログイン

1. ログイン画面が表示されます
2. デフォルトアカウントでログイン：
   - ユーザー名: `admin`
   - パスワード: `admin123`

### 4.3 パスワードを変更

> ⚠️ **重要**: すぐにパスワードを変更してください！

---

## 🎉 完了！

おめでとうございます！LMSが公開されました！

### 公開URLの例:
- `https://lms-app.onrender.com`
- `https://your-service-name.onrender.com`

### 次にすべきこと:
1. ✅ デフォルトパスワードを変更
2. ✅ 新しいユーザーを追加
3. ✅ 動画をアップロード
4. ✅ URLを共有

---

## 📝 よくある質問

### Q1: デプロイに失敗する

**A:** ログを確認してください：
- ビルドログで `requirements.txt` のエラーがないか確認
- `Procfile` と `runtime.txt` が正しく配置されているか確認
- Pythonバージョンが合っているか確認

### Q2: データベースが空っぽ

**A:** `python init_db.py` を実行し忘れていませんか？
- Renderのシェルから手動で実行してください

### Q3: 動画がアップロードできない

**A:** 無料プランの制限:
- Renderの無料プランはディスク容量が制限されています
- 大きな動画ファイルは外部ストレージ（AWS S3等）の使用を推奨

### Q4: サイトが遅い/スリープする

**A:** 無料プランの制限:
- 15分間アクセスがないとスリープします
- 初回アクセス時は起動に時間がかかります
- 有料プラン ($7/月) でスリープを無効化できます

### Q5: カスタムドメインを使いたい

**A:** Renderの有料プランで可能:
- Settings → Custom Domain で設定
- 独自ドメイン（例: `lms.yourcompany.com`）を使用可能

---

## 🔄 更新方法

コードを更新した場合：

```bash
cd "C:\Users\makoto.mizuguchi\OneDrive - Rakuten Group, Inc\CursorFiles\50Development\LMS"

# 変更をコミット
git add .
git commit -m "Update: 機能追加"

# GitHubにプッシュ
git push origin main
```

Renderが自動的に再デプロイします！

---

## 📊 無料枠の制限

### Render.com 無料プラン:
- ✅ 750時間/月の稼働時間
- ✅ 自動HTTPS
- ⚠️ 15分間アクセスなしでスリープ
- ⚠️ ディスク容量制限あり
- ⚠️ 帯域幅制限あり

### アップグレード（有料プラン）:
- $7/月: スリープなし、より高速
- カスタムドメイン対応
- より大きなディスク容量

---

## 🎯 Alternative: Railway.app

Renderが合わない場合は Railway.app も簡単です：

1. https://railway.app にアクセス
2. GitHubでログイン
3. 「New Project」→ リポジトリを選択
4. 環境変数を設定（SECRET_KEY, FLASK_ENV）
5. 自動デプロイ！

URL: `https://your-app.up.railway.app`

---

## 📞 サポート

問題が発生した場合:
1. Renderのログを確認
2. GitHubのIssueを確認
3. 開発チームに連絡

---

**Happy deploying! 🚀**
