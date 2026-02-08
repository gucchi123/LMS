# Cloudflare Tunnel セットアップガイド

このガイドでは、LMSアプリケーションをCloudflare Tunnelを使って外部公開する手順を説明します。

## 前提条件

- Cloudflareアカウント（無料）
- ドメイン（Cloudflareで管理）
- Docker Desktop for Windows

## Step 1: セキュリティ設定

外部公開前に、以下の環境変数を設定してください。

### PowerShellで環境変数を設定

```powershell
# SECRET_KEYを安全なランダム値に設定
$env:SECRET_KEY = "039b630f49f62a8a14c78966cc34018a68068974b424aa5877d4c57625a8688a"

# 本番モードに設定
$env:FLASK_ENV = "production"

# ポート設定（オプション）
$env:PORT = "5000"

# Rakuten AI APIキー（オプション - AIチャット機能用）
$env:RAKUTEN_AI_API_KEY = "your-api-key-here"
```

### または、.envファイルを作成

```
SECRET_KEY=039b630f49f62a8a14c78966cc34018a68068974b424aa5877d4c57625a8688a
FLASK_ENV=production
PORT=5000
RAKUTEN_AI_API_KEY=your-api-key-here
```

## Step 2: デフォルトパスワードの変更

⚠️ **重要**: デフォルトパスワードは必ず変更してください。

### 管理画面から変更（推奨）

1. LMSにログイン（admin/admin123）
2. 管理画面 > ユーザー管理
3. 各ユーザーのパスワードを変更

### データベースを再初期化する場合

`init_db.py`の以下の部分を変更してから実行：

```python
# Line 229: 管理者パスワード
generate_password_hash('新しい管理者パスワード')

# Line 235, 241, etc: ユーザーパスワード  
generate_password_hash('新しいユーザーパスワード')
```

## Step 3: Cloudflare Tunnel の設定

### 3.1 Cloudflareダッシュボードでトンネル作成

1. https://one.dash.cloudflare.com/ にログイン
2. **Networks** > **Tunnels** > **Create a tunnel**
3. **Cloudflared** を選択
4. トンネル名を入力（例: `lms-tunnel`）
5. **Docker** タブを選択し、コマンドをコピー

### 3.2 トンネルを実行

```powershell
# Docker Desktop が起動していることを確認

# トンネルを実行（YOUR_TOKENは上でコピーしたもの）
docker run -d --name cloudflare-lms-tunnel cloudflare/cloudflared:latest tunnel --no-autoupdate run --token YOUR_TOKEN
```

### 3.3 ルーティング設定

Cloudflareダッシュボードで：
1. トンネルの **Configure** をクリック
2. **Public Hostname** タブ
3. 以下を設定:
   - **Subdomain**: `lms`（任意）
   - **Domain**: 登録したドメイン
   - **Service Type**: `HTTP`
   - **URL**: `host.docker.internal:5000`

## Step 4: LMSアプリの起動

### 環境変数を設定してから起動

```powershell
cd "50Development/LMS"

# 環境変数を設定
$env:SECRET_KEY = "039b630f49f62a8a14c78966cc34018a68068974b424aa5877d4c57625a8688a"
$env:FLASK_ENV = "production"

# アプリを起動
python app.py
```

### または起動スクリプトを使用

```powershell
.\start_production.ps1
```

## Step 5: 動作確認

1. ブラウザで `https://lms.your-domain.com` にアクセス
2. ログイン画面が表示されることを確認
3. ログインして正常に動作することを確認

## トラブルシューティング

### トンネルが接続できない

```powershell
# コンテナのログを確認
docker logs cloudflare-lms-tunnel

# コンテナを再起動
docker restart cloudflare-lms-tunnel
```

### LMSに接続できない

1. LMSが `0.0.0.0:5000` でリッスンしていることを確認
2. ファイアウォールでポート5000が許可されていることを確認
3. Docker DesktopでWSL統合が有効になっていることを確認

### セッションが維持されない

- `SECRET_KEY`が毎回異なる値になっていないか確認
- 環境変数が正しく設定されているか確認

## 運用Tips

### トンネルの自動起動

```powershell
# Windowsスタートアップに追加
docker update --restart=always cloudflare-lms-tunnel
```

### トンネルの停止

```powershell
docker stop cloudflare-lms-tunnel
docker rm cloudflare-lms-tunnel
```

### 複数サービスの公開

同じトンネルで複数のサービスを公開できます：
- Cloudflareダッシュボードで追加のPublic Hostnameを設定
- 例: `api.your-domain.com` → `host.docker.internal:8000`

## セキュリティ注意事項

1. **SECRET_KEY**: 必ず強力なランダム値を使用
2. **パスワード**: デフォルトパスワードは必ず変更
3. **HTTPS**: Cloudflare Tunnelは自動的にHTTPSを提供
4. **アクセス制限**: 必要に応じてCloudflare Accessでアクセス制御を追加
