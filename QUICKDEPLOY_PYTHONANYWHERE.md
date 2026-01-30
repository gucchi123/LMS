# 🚀 最速デプロイガイド - PythonAnywhere版

## ⚡ 10分で公開URLを取得！

完全無料、クレジットカード不要でLMSを公開する最短ルートです。

---

## 📝 必要なもの

- [ ] GitHubアカウント（無料）
- [ ] PythonAnywhereアカウント（無料）
- [ ] 10分の時間

---

## ステップ1: GitHubにプッシュ（3分）

```bash
cd "C:\Users\makoto.mizuguchi\OneDrive - Rakuten Group, Inc\CursorFiles\50Development\LMS"

git init
git add .
git commit -m "Initial commit"

# GitHubで新規リポジトリ作成後
git remote add origin https://github.com/YOUR_USERNAME/LMS.git
git push -u origin main
```

---

## ステップ2: PythonAnywhere登録（2分）

1. https://www.pythonanywhere.com へアクセス
2. 「Create a Beginner account」（無料）
3. ユーザー名、メール、パスワードを入力
4. メール確認してログイン

---

## ステップ3: デプロイ（5分）

### 3.1 Bashコンソールを開く

ダッシュボード → 「Consoles」→「Bash」

### 3.2 コードをクローン

```bash
git clone https://github.com/YOUR_USERNAME/LMS.git
cd LMS
```

### 3.3 環境セットアップ

```bash
mkvirtualenv --python=/usr/bin/python3.10 lms-env
pip install -r requirements.txt
python init_db.py
```

### 3.4 Webアプリを作成

1. 「Web」タブ → 「Add a new web app」
2. ドメイン確認 → 「Next」
3. 「Manual configuration」→「Python 3.10」→「Next」

### 3.5 設定

**仮想環境** (「Web」タブの「Virtualenv」セクション):
```
/home/YOUR_USERNAME/.virtualenvs/lms-env
```

**WSGIファイル** (「WSGI configuration file」リンクをクリック):

すべて削除して以下をコピー（YOUR_USERNAMEを変更）:

```python
import sys
import os

path = '/home/YOUR_USERNAME/LMS'
if path not in sys.path:
    sys.path.append(path)

os.environ['SECRET_KEY'] = 'change-this-to-random-secret-key'
os.environ['FLASK_ENV'] = 'production'

from app import app as application
```

**静的ファイル** (「Static files」セクション):
- URL: `/videos`
- Path: `/home/YOUR_USERNAME/LMS/videos`

### 3.6 起動

「Reload yourusername.pythonanywhere.com」ボタンをクリック

---

## 🎉 完成！

あなたの公開URL:
```
https://yourusername.pythonanywhere.com
```

**ログイン:**
- ユーザー名: `admin`
- パスワード: `admin123`

⚠️ すぐにパスワードを変更してください！

---

## 🔄 更新方法

```bash
# ローカルで変更後
git push origin main

# PythonAnywhereのBashで
cd ~/LMS
git pull
# 「Web」タブで「Reload」
```

---

## 💰 完全無料

- ✅ クレジットカード不要
- ✅ 永久無料
- ✅ HTTPS自動
- ✅ 24時間稼働

---

## 📞 問題が発生したら

詳細ガイド: `DEPLOY_PYTHONANYWHERE.md` を参照

---

**これで完成です！🎊**
