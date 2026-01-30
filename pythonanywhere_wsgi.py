# PythonAnywhere WSGI Configuration File
# このファイルはPythonAnywhereのWSGI設定用のテンプレートです
# 
# 使い方:
# 1. PythonAnywhereの「Web」タブで「WSGI configuration file」をクリック
# 2. 既存の内容をすべて削除
# 3. このファイルの内容をコピー
# 4. YOUR_USERNAMEを実際のPythonAnywhereユーザー名に変更
# 5. SECRET_KEYを強力なランダム文字列に変更
# 6. 保存

import sys
import os

# ========================================
# 設定: ここを変更してください
# ========================================

# YOUR_USERNAMEを実際のPythonAnywhereユーザー名に変更
USERNAME = 'YOUR_USERNAME'  # 例: 'mizuguchi'

# SECRET_KEYを強力なランダム文字列に変更
# 生成方法: import secrets; print(secrets.token_hex(32))
SECRET_KEY = 'your-strong-random-secret-key-here'

# ========================================
# 以下は変更不要
# ========================================

# LMSディレクトリへのパスを追加
path = f'/home/{USERNAME}/LMS'
if path not in sys.path:
    sys.path.append(path)

# 環境変数を設定
os.environ['SECRET_KEY'] = SECRET_KEY
os.environ['FLASK_ENV'] = 'production'

# 作業ディレクトリを変更（データベースファイルのため）
os.chdir(path)

# Flaskアプリをインポート
from app import app as application

# ログ設定（デバッグ用）
import logging
logging.basicConfig(level=logging.INFO)
application.logger.info('LMS Application started on PythonAnywhere')
