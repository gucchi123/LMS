# 🐍 PythonAnywhere デプロイガイド（無料）

PythonAnywhereで無料でLMSをデプロイして公開URLを取得する完全ガイドです。

---

## ✅ PythonAnywhereの無料プランについて

### 完全無料で使える機能：
- ✅ **永久無料**（クレジットカード不要）
- ✅ 公開URL: `https://yourusername.pythonanywhere.com`
- ✅ Python専用ホスティング
- ✅ SQLiteデータベース対応
- ✅ 24時間365日稼働（スリープなし）
- ✅ HTTPSサポート
- ✅ 1つのWebアプリ

### 無料プランの制限：
- ⚠️ CPU時間: 100秒/日
- ⚠️ ディスク容量: 512MB
- ⚠️ 外部APIへのアクセス制限（ホワイトリストのみ）
- ⚠️ カスタムドメイン不可（有料プランで可能）

### 🎯 LMSに最適な理由：
- SQLiteをそのまま使用可能
- Flaskアプリに最適化
- Python環境が簡単にセットアップできる
- スリープしない（常時稼働）

---

## 📋 事前準備

- [ ] PythonAnywhereアカウント（無料）
- [ ] GitHubアカウント
- [ ] LMSコードをGitHubにプッシュ済み

---

## ステップ1️⃣: GitHubにコードをプッシュ

### 1.1 まだGitHubにプッシュしていない場合

```bash
cd "C:\Users\makoto.mizuguchi\OneDrive - Rakuten Group, Inc\CursorFiles\50Development\LMS"

# Git初期化
git init

# .gitignoreを確認（大きな動画ファイルは除外される）
git add .
git commit -m "Initial commit: LMS for PythonAnywhere"

# GitHubリポジトリを作成後、リモートを追加
git remote add origin https://github.com/YOUR_USERNAME/LMS.git
git push -u origin main
```

---

## ステップ2️⃣: PythonAnywhereにサインアップ

### 2.1 アカウント作成

1. https://www.pythonanywhere.com にアクセス
2. 「Start running Python online in less than a minute!」の下の「Create a Beginner account」をクリック
3. フォームに入力：
   - **Username**: 任意のユーザー名（公開URLになります）
   - **Email**: メールアドレス
   - **Password**: パスワード
4. 「Register」をクリック
5. メール確認（届いたメール内のリンクをクリック）

### 2.2 ログイン

https://www.pythonanywhere.com/login/ からログイン

---

## ステップ3️⃣: コードをPythonAnywhereにアップロード

### 3.1 Bashコンソールを開く

1. ダッシュボードで「Consoles」タブをクリック
2. 「Bash」をクリック（新しいBashコンソールが開きます）

### 3.2 GitHubからクローン

Bashコンソールで以下のコマンドを実行：

```bash
# ホームディレクトリにいることを確認
cd ~

# GitHubリポジトリをクローン
git clone https://github.com/YOUR_USERNAME/LMS.git

# 例:
# git clone https://github.com/makoto-mizuguchi/LMS.git

# LMSディレクトリに移動
cd LMS

# ファイルを確認
ls -la
```

---

## ステップ4️⃣: 仮想環境とパッケージのセットアップ

### 4.1 仮想環境を作成

```bash
# Python 3.10の仮想環境を作成
mkvirtualenv --python=/usr/bin/python3.10 lms-env

# 仮想環境がアクティブになったことを確認（プロンプトに(lms-env)と表示される）
```

### 4.2 必要なパッケージをインストール

```bash
# LMSディレクトリにいることを確認
cd ~/LMS

# パッケージをインストール
pip install -r requirements.txt
```

### 4.3 データベースを初期化

```bash
# データベースを初期化
python init_db.py
```

以下のようなメッセージが表示されればOK：
```
=== データベースの初期化が完了しました ===

デフォルトアカウント:
  管理者:
    ユーザー名: admin
    パスワード: admin123
...
```

---

## ステップ5️⃣: Webアプリを設定

### 5.1 Webアプリを作成

1. PythonAnywhereのダッシュボードに戻る
2. 「Web」タブをクリック
3. 「Add a new web app」をクリック
4. ドメイン名を確認（`yourusername.pythonanywhere.com`）→「Next」
5. 「Manual configuration」を選択
6. 「Python 3.10」を選択
7. 「Next」をクリック

### 5.2 仮想環境のパスを設定

「Web」タブの「Virtualenv」セクション：

1. 「Enter path to a virtualenv, if desired」の下のリンクをクリック
2. 以下のパスを入力：
   ```
   /home/YOUR_USERNAME/.virtualenvs/lms-env
   ```
   例: `/home/mizuguchi/.virtualenvs/lms-env`
3. チェックマークをクリック

### 5.3 WSGIファイルを編集

「Web」タブの「Code」セクション：

1. 「WSGI configuration file」のリンクをクリック（例: `/var/www/yourusername_pythonanywhere_com_wsgi.py`）
2. ファイルの内容を**すべて削除**
3. 以下の内容に置き換え：

```python
import sys
import os

# LMSディレクトリへのパスを追加（YOUR_USERNAMEを実際のユーザー名に変更）
path = '/home/YOUR_USERNAME/LMS'
if path not in sys.path:
    sys.path.append(path)

# 環境変数を設定
os.environ['SECRET_KEY'] = 'your-strong-random-secret-key-here'
os.environ['FLASK_ENV'] = 'production'

# Flaskアプリをインポート
from app import app as application
```

**重要**: 
- `YOUR_USERNAME` を実際のPythonAnywhereユーザー名に変更
- `your-strong-random-secret-key-here` を強力なランダム文字列に変更

Secret Keyの生成方法（ローカルPythonで実行）:
```python
import secrets
print(secrets.token_hex(32))
```
Key
6d616201a259ea3b252ec26e501530b94078cfba27bbafd15cc6f97d651ae929


4. 「Save」をクリック

### 5.4 静的ファイルを設定

「Web」タブの「Static files」セクション：

1. 「Enter URL」に `/videos` と入力
2. 「Enter path」に `/home/YOUR_USERNAME/LMS/videos` と入力
3. チェックマークをクリック

---

## ステップ6️⃣: アプリを起動

### 6.1 Webアプリをリロード

1. 「Web」タブの一番上に戻る
2. 大きな緑色の「Reload yourusername.pythonanywhere.com」ボタンをクリック

### 6.2 公開URLにアクセス

ブラウザで以下のURLを開く：
```
https://yourusername.pythonanywhere.com
```

（`yourusername` は実際のPythonAnywhereユーザー名）

---

## ステップ7️⃣: ログインして確認

### 7.1 初回ログイン

1. ログイン画面が表示されます
2. デフォルトアカウントでログイン：
   - **ユーザー名**: `admin`
   - **パスワード**: `admin123`

### 7.2 パスワードを変更

⚠️ **重要**: 必ずパスワードを変更してください！

---

## 🎉 完了！

おめでとうございます！LMSが公開されました！

### あなたの公開URL:
```
https://yourusername.pythonanywhere.com
```

### 次にすべきこと:
1. ✅ デフォルトパスワードを変更
2. ✅ 新しいユーザーを追加
3. ✅ 動画をアップロード（管理画面から）
4. ✅ URLを共有

---

## 🔄 更新方法（コードを変更した場合）

### GitHubにプッシュしてPythonAnywhereで更新：

```bash
# ローカルで変更をコミット&プッシュ
cd "50Development/LMS"
git add .
git commit -m "Update: 新機能追加"
git push origin main

# PythonAnywhereのBashコンソールで：
cd ~/LMS
git pull origin main

# 必要に応じて
pip install -r requirements.txt

# Webアプリをリロード
# →「Web」タブの「Reload」ボタンをクリック
```

---

## 🆘 トラブルシューティング

### エラー: "Something went wrong :-("

**原因**: WSGIファイルの設定ミス

**解決方法**:
1. 「Web」タブの「Error log」をクリック
2. エラーメッセージを確認
3. よくある問題：
   - パスが間違っている（ユーザー名の間違い）
   - インデントが間違っている（Pythonはインデント重要）
   - `from app import app` が失敗（パスが正しくない）

### エラー: "ModuleNotFoundError: No module named 'flask'"

**原因**: 仮想環境が正しく設定されていない

**解決方法**:
1. Bashコンソールで：
   ```bash
   workon lms-env
   cd ~/LMS
   pip install -r requirements.txt
   ```
2. 「Web」タブで仮想環境のパスを確認

### データベースが空

**原因**: `init_db.py` を実行していない

**解決方法**:
```bash
workon lms-env
cd ~/LMS
python init_db.py
```

### 動画がアップロードできない

**原因**: 無料プランのディスク容量制限（512MB）

**解決方法**:
1. ディスク使用量を確認：「Files」タブで確認
2. 小さい動画を使用（50MB以下推奨）
3. 有料プラン（$5/月）にアップグレード

### ログファイルの確認方法

1. 「Web」タブをクリック
2. 「Log files」セクションで以下を確認：
   - **Error log**: エラーメッセージ
   - **Server log**: アクセスログ
   - **Access log**: アクセス履歴

---

## 📊 無料プランで十分？

### 無料プランで十分なケース：
- ✅ 小規模チーム（10人以下）
- ✅ 動画数が少ない（5-10本程度）
- ✅ 社内テスト・デモ用途
- ✅ 低トラフィック

### 有料プランを検討すべきケース：
- ❌ 大量の動画（100本以上）
- ❌ 高トラフィック（同時アクセス多数）
- ❌ カスタムドメイン必要
- ❌ 外部API連携が必要

### 有料プラン料金：
- **Hacker**: $5/月（1GB、より多くのCPU）
- **Web Dev**: $12/月（3GB、カスタムドメイン可）

---

## 💡 ディスク容量を節約する方法

### 1. 大きな動画ファイルをGitHubに含めない
`.gitignore` に既に設定済み：
```
videos/*
!videos/.gitkeep
```

### 2. 動画を圧縮
- HandBrakeなどで動画を圧縮
- 解像度を下げる（720p推奨）
- ビットレートを調整

### 3. 外部ストレージを使用
有料プランの場合：
- YouTube（埋め込み）
- Vimeo
- AWS S3
- Cloudinary

---

## 🔐 セキュリティ設定

### 1. SECRET_KEYを強力にする

WSGIファイルで設定：
```python
os.environ['SECRET_KEY'] = 'ここに64文字以上のランダム文字列'
```

### 2. パスワードを変更

デフォルトパスワードは必ず変更してください！

### 3. HTTPSを使用

PythonAnywhereは自動的にHTTPSを提供します（無料）

---

## 📞 サポート

### PythonAnywhereヘルプ:
- フォーラム: https://www.pythonanywhere.com/forums/
- ヘルプページ: https://help.pythonanywhere.com/

### LMSに関する質問:
- 開発チームに連絡

---

## 🎯 まとめ

### 手順おさらい:
1. ✅ GitHubにプッシュ
2. ✅ PythonAnywhereアカウント作成（無料）
3. ✅ Bashコンソールで `git clone`
4. ✅ 仮想環境作成 & パッケージインストール
5. ✅ データベース初期化
6. ✅ Webアプリ設定（WSGI編集）
7. ✅ Reload → 公開！

### あなたの公開URL:
```
https://yourusername.pythonanywhere.com
```

**完全無料、クレジットカード不要、永久使用可能！** 🎉

---

**Happy deploying with PythonAnywhere! 🐍✨**
