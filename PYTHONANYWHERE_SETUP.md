# PythonAnywhere デプロイ手順

## 1. GitHubから最新コードを取得

PythonAnywhereのBashコンソールで実行：

```bash
cd ~/mysite
git pull origin main
```

## 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt --user
```

## 3. 環境変数の設定

### 方法A: WSGIファイルに設定（推奨）

1. **Web** タブ → **WSGI configuration file** をクリック
2. ファイルの先頭に以下を追加：

```python
import os
import sys

# 環境変数を設定（重要：実際のAPIキーに置き換えてください）
os.environ['RAKUTEN_AI_API_KEY'] = 'raik-pat-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
os.environ['RAKUTEN_AI_BASE_URL'] = 'https://api.ai.public.rakuten-it.com/rakutenllms/v1/'
os.environ['RAKUTEN_AI_MODEL'] = 'rakutenai-3.0'
os.environ['SECRET_KEY'] = 'your-production-secret-key-here'
os.environ['FLASK_ENV'] = 'production'

# プロジェクトパスを追加
path = '/home/yourusername/mysite'
if path not in sys.path:
    sys.path.append(path)

# アプリをインポート
from app import app as application
```

### 方法B: .envファイルを使用

Bashコンソールで実行：

```bash
cd ~/mysite
cat > .env << 'EOF'
RAKUTEN_AI_API_KEY=raik-pat-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RAKUTEN_AI_BASE_URL=https://api.ai.public.rakuten-it.com/rakutenllms/v1/
RAKUTEN_AI_MODEL=rakutenai-3.0
SECRET_KEY=your-production-secret-key-here
FLASK_ENV=production
EOF
```

## 4. データベースの初期化（初回のみ）

```bash
cd ~/mysite
python init_db.py
```

## 5. Webアプリの再読み込み

**Web** タブ → **Reload** ボタンをクリック

---

## トラブルシューティング

### APIキーが認識されない場合

1. WSGIファイルの設定が正しいか確認
2. Webアプリを再読み込み
3. エラーログを確認：**Web** タブ → **Error log**

### pykakasi のインストールエラー

```bash
pip install pykakasi --user
```

### 日本語が文字化けする場合

WSGIファイルに追加：

```python
import sys
sys.stdout.reconfigure(encoding='utf-8')
```

---

## 環境変数一覧

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `RAKUTEN_AI_API_KEY` | Rakuten AI 3.0 APIキー | ✅ |
| `RAKUTEN_AI_BASE_URL` | APIエンドポイント | - |
| `RAKUTEN_AI_MODEL` | 使用モデル名 | - |
| `SECRET_KEY` | Flaskセッション暗号化キー | ✅ |
| `FLASK_ENV` | 環境（production/development） | - |
