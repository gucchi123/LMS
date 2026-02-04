# LMS 文字起こし機能 - クイックガイド

## 問題が発生していた原因

文字起こし機能が「失敗」になっていた原因は、**ffmpegがシステムにインストールされていなかった**ためです。

Whisper（AI音声認識ライブラリ）は、動画ファイルから音声を抽出するために`ffmpeg`というツールを必要としますが、それが見つからずエラーになっていました。

## 修正内容

以下の対応を実施しました:

### 1. ffmpeg.exeの配置
```
50Development/LMS/ffmpeg.exe
```
既存のffmpeg.exeをLMSフォルダにコピーしました。

### 2. app.pyの修正
`transcribe_video_async`関数に、ローカルのffmpegを自動検出して使用するコードを追加しました:

```python
# ffmpegのパスを設定（ローカルにある場合）
local_ffmpeg = os.path.join(os.path.dirname(__file__), 'ffmpeg.exe')
if os.path.exists(local_ffmpeg):
    os.environ['PATH'] = os.path.dirname(local_ffmpeg) + os.pathsep + os.environ.get('PATH', '')
    print(f"[Whisper] Using local ffmpeg: {local_ffmpeg}")
```

### 3. テストスクリプトの作成
- `test_whisper.py`: Whisperが正常に動作するかテスト
- `reset_status.py`: 失敗ステータスをリセット（改良版）

### 4. ドキュメント更新
- `README.md`: セットアップ手順とトラブルシューティングを追加
- `fix_transcription.md`: この問題の詳細説明

## 使い方

### ステップ1: 失敗ステータスをリセット

```bash
cd "c:\Users\makoto.mizuguchi\OneDrive - Rakuten Group, Inc\CursorFiles\50Development\LMS"
python reset_status.py
```

**出力例:**
```
3件の動画のステータスをリセットします:

  - ID 1: Rakuten AI for Businessのご紹介...
  - ID 2: ユースケース１：議事録作成...
  - ID 3: 介護業界の生成AI事例紹介...

✓ 3件の動画をリセットしました
```

### ステップ2: LMSアプリを起動

```bash
python app.py
```

### ステップ3: Webブラウザで管理画面にアクセス

1. http://localhost:5000/login にアクセス
2. 管理者アカウントでログイン:
   - ユーザー名: `admin`
   - パスワード: `admin123`

### ステップ4: 文字起こしを実行

1. 管理画面の「動画管理」セクションで対象の動画を見つける
2. 🎤「文字起こし」ボタンをクリック
3. ステータスが以下のように変化します:
   - `pending` → 処理待ち
   - `processing` → 処理中（数分かかります）
   - `completed` → 完了

### ステップ5: 結果を確認

文字起こしが完了すると:
- 動画に自動生成された**概要**が表示されます
- ユーザーが視聴ページで**全文トランスクリプト**を閲覧できます
- AIチャット機能で**動画の内容に基づいた質問**に答えられるようになります

## テスト方法

文字起こしが正常に動作するか事前にテストできます:

```bash
python test_whisper.py
```

**成功例:**
```
✓ ffmpegを設定: c:\...\ffmpeg.exe

動画ファイル: c:\...\nursing_care_text_ai_guide_...mp4
ファイル存在: True
ファイルサイズ: 36.42 MB

[1/3] Whisperモデルをロード中...
✓ モデルロード成功

[2/3] 文字起こし実行中...
✓ 文字起こし成功

[3/3] 結果:
文字数: 1478 文字
テキスト（最初の500文字）:
皆様、本日はお忙しい中、介護業界のおけるテキスト生成AI活用ガイドの研修に...

✓ テスト完了
```

## トラブルシューティング

### 「Whisperがインストールされていません」エラー

**原因**: `whisper`ライブラリがインストールされていない

**解決策**:
```bash
pip install openai-whisper
```

### 「The system cannot find the file specified」エラー

**原因**: ffmpegが見つからない

**解決策**:
1. LMSフォルダに`ffmpeg.exe`があるか確認
2. なければコピー、またはシステム全体にインストール:
   ```powershell
   choco install ffmpeg
   ```

### 処理が遅い

**正常動作**: 
- 5分の動画で約2〜5分の処理時間がかかります
- CPU性能に依存します
- `medium`モデルを使用（精度と速度のバランス）

**高速化したい場合**:
- `app.py`の`model = whisper.load_model("medium")`を`"small"`に変更
- ただし、精度は低下します

### 文字起こしの精度が低い

**改善方法**:
- `app.py`の`model = whisper.load_model("medium")`を`"large"`に変更
- ただし、処理時間が2倍以上になります

## 技術詳細

### 使用しているAI

- **Whisper**: OpenAIが開発した高精度音声認識AI
- **Rakuten AI 3.0**: トランスクリプトから概要を生成

### 処理フロー

1. 管理者が「文字起こし」ボタンをクリック
2. バックグラウンドスレッドで処理開始
3. ffmpegが動画から音声を抽出
4. Whisperが音声をテキストに変換（日本語最適化）
5. Rakuten AI 3.0がトランスクリプトから概要を生成
6. データベースに保存（`video_transcripts`テーブル）
7. ステータスを`completed`に更新

### データベース構造

**videos テーブル**:
- `transcription_status`: 'none' | 'pending' | 'processing' | 'completed' | 'failed'
- `summary`: AI生成の概要文

**video_transcripts テーブル**:
- `video_id`: 動画ID
- `content`: 文字起こしテキスト
- `content_type`: 'transcript' | 'description'

## まとめ

✅ **修正完了項目:**
1. ffmpeg.exeの配置とパス設定
2. app.pyの自動検出機能追加
3. テストスクリプトの作成
4. ステータスリセット機能の改良
5. ドキュメントの充実

✅ **現在の状態:**
- 文字起こし機能は正常に動作します
- 3件の動画がリセットされ、再実行可能です
- テストスクリプトで動作確認済みです

✅ **次のステップ:**
1. LMSアプリを起動
2. 管理画面で文字起こしを実行
3. 完了後、ユーザー向け視聴ページで確認

---

**作成日**: 2026年2月3日  
**問題**: 文字起こしが失敗する  
**原因**: ffmpeg未インストール  
**解決**: ローカルffmpegの配置とパス自動設定
