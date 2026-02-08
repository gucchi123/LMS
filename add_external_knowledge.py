"""
外部ナレッジをデータベースに追加するスクリプト

使用方法:
    python add_external_knowledge.py

機能:
- external_knowledge テーブルを作成（存在しない場合）
- Markdownファイルからナレッジを抽出してデータベースに挿入
"""

import sqlite3
import os
import sys
import re

# Windows環境での日本語出力対応
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


def create_external_knowledge_table(cursor):
    """外部ナレッジテーブルを作成"""
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS external_knowledge (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        industry_id INTEGER,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source_file TEXT,
        section TEXT,
        keywords TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (industry_id) REFERENCES industries (id)
    )
    ''')
    print("✅ external_knowledge テーブルを作成/確認しました")


def get_industry_id(cursor, industry_name):
    """業種名からIDを取得"""
    result = cursor.execute(
        'SELECT id FROM industries WHERE name = ?', 
        (industry_name,)
    ).fetchone()
    return result[0] if result else None


def parse_markdown_sections(content, source_file):
    """Markdownファイルをセクションごとに分割"""
    sections = []
    current_section = None
    current_content = []
    
    lines = content.split('\n')
    
    for line in lines:
        # h2 または h3 のヘッダーを検出
        h2_match = re.match(r'^## (.+)$', line)
        h3_match = re.match(r'^### (.+)$', line)
        
        if h2_match or h3_match:
            # 前のセクションを保存
            if current_section and current_content:
                sections.append({
                    'title': current_section,
                    'content': '\n'.join(current_content).strip(),
                    'source_file': source_file
                })
            
            current_section = h2_match.group(1) if h2_match else h3_match.group(1)
            # マークダウンの装飾を削除
            current_section = re.sub(r'\*\*(.+?)\*\*', r'\1', current_section)
            current_section = current_section.strip()
            current_content = []
        else:
            current_content.append(line)
    
    # 最後のセクションを保存
    if current_section and current_content:
        sections.append({
            'title': current_section,
            'content': '\n'.join(current_content).strip(),
            'source_file': source_file
        })
    
    return sections


def extract_keywords(content):
    """コンテンツからキーワードを抽出"""
    # 太字のテキストをキーワードとして抽出
    bold_keywords = re.findall(r'\*\*(.+?)\*\*', content)
    
    # 業界特有のキーワード
    industry_keywords = [
        '介護', 'ケアプラン', '記録', '文字起こし', '音声', 'AI', '自動化',
        '効率化', '削減', '支援', 'システム', 'モニタリング', '見守り',
        '高齢者', '福祉', 'ケアマネ', '介護職員', '人手不足'
    ]
    
    found_keywords = []
    for kw in industry_keywords:
        if kw in content:
            found_keywords.append(kw)
    
    # 太字キーワードと業界キーワードを結合
    all_keywords = list(set(bold_keywords[:5] + found_keywords[:10]))
    
    return ','.join(all_keywords[:10])


def insert_knowledge(cursor, industry_id, sections):
    """ナレッジをデータベースに挿入"""
    inserted = 0
    for section in sections:
        if len(section['content']) < 50:  # 短すぎるセクションはスキップ
            continue
        
        keywords = extract_keywords(section['content'])
        
        cursor.execute('''
            INSERT INTO external_knowledge 
            (industry_id, title, content, source_file, section, keywords)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            industry_id,
            section['title'],
            section['content'],
            section['source_file'],
            section['title'],
            keywords
        ))
        inserted += 1
    
    return inserted


def clear_existing_knowledge(cursor, source_files):
    """既存のナレッジを削除（同じソースファイルのもののみ）"""
    for source_file in source_files:
        cursor.execute(
            'DELETE FROM external_knowledge WHERE source_file = ?',
            (source_file,)
        )


def main():
    # データベース接続
    db_path = 'lms.db'
    if not os.path.exists(db_path):
        print("❌ lms.db が見つかりません。先に python init_db.py を実行してください。")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # テーブル作成
    create_external_knowledge_table(cursor)
    
    # 介護業界のIDを取得
    nursing_id = get_industry_id(cursor, '介護')
    if not nursing_id:
        print("❌ 介護業界が見つかりません")
        conn.close()
        return
    
    print(f"📋 介護業界ID: {nursing_id}")
    
    # ナレッジファイルのパス（ワークスペースルートからの相対パス）
    # スクリプトの場所: 50Development/LMS/
    # ターゲットの場所: 04AIDD/02AIDC/AI4B/FocusedIndustry/
    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    knowledge_files = [
        {
            'path': os.path.join(workspace_root, '04AIDD', '02AIDC', 'AI4B', 'FocusedIndustry', '01_介護業界_UseCases.md'),
            'name': '01_介護業界_UseCases.md'
        },
        {
            'path': os.path.join(workspace_root, '04AIDD', '02AIDC', 'AI4B', 'FocusedIndustry', '業界別詳細_01_介護_テキストAI事例.md'),
            'name': '業界別詳細_01_介護_テキストAI事例.md'
        }
    ]
    
    # 既存のナレッジを削除
    clear_existing_knowledge(cursor, [f['name'] for f in knowledge_files])
    
    total_inserted = 0
    
    for file_info in knowledge_files:
        file_path = file_info['path']
        
        if not os.path.exists(file_path):
            print(f"⚠️ ファイルが見つかりません: {file_path}")
            continue
        
        print(f"\n📖 読み込み中: {file_info['name']}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # セクションに分割
        sections = parse_markdown_sections(content, file_info['name'])
        print(f"   セクション数: {len(sections)}")
        
        # データベースに挿入
        inserted = insert_knowledge(cursor, nursing_id, sections)
        total_inserted += inserted
        print(f"   挿入数: {inserted}")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ 完了! 合計 {total_inserted} 件のナレッジを追加しました")
    print("\n📚 追加されたナレッジの確認:")
    
    # 確認のため再接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    results = cursor.execute('''
        SELECT title, substr(content, 1, 50) as preview, source_file
        FROM external_knowledge
        WHERE industry_id = ?
        ORDER BY id
    ''', (nursing_id,)).fetchall()
    
    for title, preview, source in results:
        print(f"  - [{source}] {title}")
        print(f"    {preview}...")
    
    conn.close()


if __name__ == '__main__':
    main()
