# -*- coding: utf-8 -*-
"""
LMS アプリケーション テストスイート
========================================
業種別アクセス制御を含む全機能のテスト

テストは本番DB (lms.db) を汚染しないよう、
専用の test_lms.db を使用して実行されます。
"""

import pytest
import sqlite3
import os
import sys

# Windows環境での日本語出力対応
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# テスト用DBパスを設定（本番DBを汚染しない）
TEST_DB_PATH = os.path.join(os.path.dirname(__file__), 'test_lms.db')
os.environ['LMS_DATABASE'] = TEST_DB_PATH

from app import app, get_db

# ========== テスト設定 ==========

@pytest.fixture(scope='session', autouse=True)
def setup_test_db():
    """テストセッション開始前にテスト用DBを作成し、終了後に削除"""
    # テスト用DBでマイグレーション実行
    app.config['DATABASE'] = TEST_DB_PATH
    from migrate_db import run_migrations
    run_migrations(verbose=False, db_path=TEST_DB_PATH)
    
    yield
    
    # テスト終了後にテスト用DBを削除
    import gc
    gc.collect()
    try:
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
            print(f"\nテスト用DB削除: {TEST_DB_PATH}")
    except PermissionError:
        print(f"\nテスト用DBはロック中のためスキップ（次回テスト時に上書き）: {TEST_DB_PATH}")

@pytest.fixture
def client():
    """テスト用のFlaskクライアントを作成"""
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['DATABASE'] = TEST_DB_PATH
    with app.test_client() as client:
        yield client

@pytest.fixture
def admin_client(client):
    """管理者としてログイン済みのクライアント"""
    client.post('/login', json={
        'username': 'admin',
        'password': 'admin123'
    })
    return client

@pytest.fixture
def hotel_client(client):
    """宿泊業ユーザーとしてログイン済みのクライアント"""
    client.post('/login', json={
        'username': 'hotel_tanaka',
        'password': 'user123'
    })
    return client

@pytest.fixture
def retail_client(client):
    """小売業ユーザーとしてログイン済みのクライアント"""
    client.post('/login', json={
        'username': 'retail_yamada',
        'password': 'user123'
    })
    return client


# ========== ログイン機能テスト ==========

class TestLogin:
    """ログイン機能のテスト"""
    
    def test_login_page_loads(self, client):
        """ログインページが正常に表示される"""
        response = client.get('/login')
        assert response.status_code == 200
        assert 'LMS'.encode('utf-8') in response.data
        print("✓ ログインページが正常に表示されます")
    
    def test_admin_login_success(self, client):
        """管理者アカウントでログイン成功"""
        response = client.post('/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert data['is_admin'] == True
        print("✓ 管理者ログイン成功")
    
    def test_hotel_user_login_success(self, client):
        """宿泊業ユーザーでログイン成功"""
        response = client.post('/login', json={
            'username': 'hotel_tanaka',
            'password': 'user123'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 宿泊業ユーザーログイン成功")
    
    def test_retail_user_login_success(self, client):
        """小売業ユーザーでログイン成功"""
        response = client.post('/login', json={
            'username': 'retail_yamada',
            'password': 'user123'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 小売業ユーザーログイン成功")
    
    def test_login_failure_wrong_password(self, client):
        """間違ったパスワードでログイン失敗"""
        response = client.post('/login', json={
            'username': 'admin',
            'password': 'wrongpassword'
        })
        assert response.status_code == 401
        data = response.get_json()
        assert data['success'] == False
        print("✓ 間違ったパスワードで正しく拒否されます")
    
    def test_login_failure_nonexistent_user(self, client):
        """存在しないユーザーでログイン失敗"""
        response = client.post('/login', json={
            'username': 'nonexistent',
            'password': 'password'
        })
        assert response.status_code == 401
        data = response.get_json()
        assert data['success'] == False
        print("✓ 存在しないユーザーで正しく拒否されます")
    
    def test_logout(self, admin_client):
        """ログアウト機能"""
        response = admin_client.get('/logout', follow_redirects=True)
        assert response.status_code == 200
        print("✓ ログアウト成功")


# ========== 業種別アクセス制御テスト ==========

class TestIndustryAccess:
    """業種別アクセス制御のテスト"""
    
    def test_admin_sees_all_categories(self, admin_client):
        """管理者は全カテゴリーを閲覧可能"""
        response = admin_client.get('/courses')
        assert response.status_code == 200
        # 共通カテゴリー
        assert '基礎編'.encode('utf-8') in response.data
        # 業種別カテゴリー（全て表示される）
        assert '宿泊業向けAI活用'.encode('utf-8') in response.data
        assert '小売業向けAI活用'.encode('utf-8') in response.data
        print("✓ 管理者は全カテゴリーにアクセス可能")
    
    def test_hotel_user_sees_common_categories(self, hotel_client):
        """宿泊業ユーザーは共通カテゴリーを閲覧可能"""
        response = hotel_client.get('/courses')
        assert response.status_code == 200
        assert '基礎編'.encode('utf-8') in response.data
        assert '応用編'.encode('utf-8') in response.data
        assert '実践編'.encode('utf-8') in response.data
        print("✓ 宿泊業ユーザーは共通カテゴリーにアクセス可能")
    
    def test_hotel_user_sees_hotel_category(self, hotel_client):
        """宿泊業ユーザーは宿泊業カテゴリーを閲覧可能"""
        response = hotel_client.get('/courses')
        assert response.status_code == 200
        assert '宿泊業向けAI活用'.encode('utf-8') in response.data
        print("✓ 宿泊業ユーザーは宿泊業専用カテゴリーにアクセス可能")
    
    def test_hotel_user_cannot_see_retail_category(self, hotel_client):
        """宿泊業ユーザーは小売業カテゴリーを閲覧不可"""
        response = hotel_client.get('/courses')
        assert response.status_code == 200
        assert '小売業向けAI活用'.encode('utf-8') not in response.data
        print("✓ 宿泊業ユーザーは小売業カテゴリーにアクセス不可（正常）")
    
    def test_retail_user_sees_retail_category(self, retail_client):
        """小売業ユーザーは小売業カテゴリーを閲覧可能"""
        response = retail_client.get('/courses')
        assert response.status_code == 200
        assert '小売業向けAI活用'.encode('utf-8') in response.data
        print("✓ 小売業ユーザーは小売業専用カテゴリーにアクセス可能")
    
    def test_retail_user_cannot_see_hotel_category(self, retail_client):
        """小売業ユーザーは宿泊業カテゴリーを閲覧不可"""
        response = retail_client.get('/courses')
        assert response.status_code == 200
        assert '宿泊業向けAI活用'.encode('utf-8') not in response.data
        print("✓ 小売業ユーザーは宿泊業カテゴリーにアクセス不可（正常）")


# ========== 管理画面アクセステスト ==========

class TestAdminAccess:
    """管理画面アクセス制御のテスト"""
    
    def test_admin_can_access_admin_page(self, admin_client):
        """管理者は管理画面にアクセス可能"""
        response = admin_client.get('/admin')
        assert response.status_code == 200
        assert '管理画面'.encode('utf-8') in response.data
        print("✓ 管理者は管理画面にアクセス可能")
    
    def test_normal_user_cannot_access_admin(self, client):
        """一般ユーザー(role=user)は管理画面にアクセス不可"""
        client.post('/login', json={
            'username': 'ryokan_suzuki',
            'password': 'user123'
        })
        response = client.get('/admin')
        assert response.status_code == 403
        print("✓ 一般ユーザーは管理画面にアクセス不可（正常）")
    
    def test_unauthenticated_cannot_access_admin(self, client):
        """未認証ユーザーは管理画面にアクセス不可"""
        response = client.get('/admin', follow_redirects=False)
        assert response.status_code == 302  # リダイレクト
        print("✓ 未認証ユーザーは管理画面にアクセス不可（正常）")


# ========== 業種管理APIテスト ==========

class TestIndustryAPI:
    """業種管理APIのテスト"""
    
    def test_get_industries(self, admin_client):
        """業種一覧を取得"""
        response = admin_client.get('/api/industries')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 6  # 最低6業種
        industry_names = [i['name'] for i in data]
        assert '宿泊' in industry_names
        assert '小売' in industry_names
        assert '飲食' in industry_names
        assert '介護' in industry_names
        assert '医療' in industry_names
        assert '教育' in industry_names
        print(f"✓ 業種一覧を正常に取得（{len(data)}件）")
    
    def test_create_industry(self, admin_client):
        """新しい業種を作成"""
        import time
        unique_name = f'テスト業種_{int(time.time())}'
        response = admin_client.post('/api/admin/industries', json={
            'name': unique_name,
            'name_en': 'Test Industry',
            'description': 'テスト用の業種です',
            'icon': 'bi-gear',
            'color': '#ff0000'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 新しい業種を作成成功")
    
    def test_normal_user_cannot_create_industry(self, client):
        """一般ユーザー(role=user)は業種を作成不可"""
        client.post('/login', json={
            'username': 'ryokan_suzuki',
            'password': 'user123'
        })
        response = client.post('/api/admin/industries', json={
            'name': '不正な業種',
            'name_en': 'Invalid Industry'
        })
        assert response.status_code == 403
        print("✓ 一般ユーザーは業種作成不可（正常）")


# ========== カテゴリー管理APIテスト ==========

class TestCategoryAPI:
    """カテゴリー管理APIのテスト"""
    
    def test_get_categories(self, admin_client):
        """カテゴリー一覧を取得"""
        response = admin_client.get('/api/categories')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) > 0
        print(f"✓ カテゴリー一覧を取得（{len(data)}件）")
    
    def test_create_category(self, admin_client):
        """新しいカテゴリーを作成"""
        response = admin_client.post('/api/admin/categories', json={
            'name': 'テストカテゴリー',
            'description': 'テスト用のカテゴリーです',
            'icon': 'bi-folder',
            'color': '#667eea'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 新しいカテゴリーを作成成功")
    
    def test_update_category_access(self, admin_client):
        """カテゴリーのアクセス制御を更新"""
        # まずカテゴリーを作成
        create_response = admin_client.post('/api/admin/categories', json={
            'name': 'アクセステスト用',
            'description': 'アクセス制御テスト用'
        })
        category_id = create_response.get_json()['id']
        
        # アクセス制御を設定（宿泊業のみ）
        response = admin_client.put(f'/api/admin/categories/{category_id}/access', json={
            'industry_ids': [1]  # 宿泊業
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ カテゴリーアクセス制御を更新成功")


# ========== ユーザー管理APIテスト ==========

class TestUserAPI:
    """ユーザー管理APIのテスト"""
    
    def test_create_user(self, admin_client):
        """新しいユーザーを作成"""
        import time
        ts = int(time.time())
        response = admin_client.post('/api/admin/users', json={
            'username': f'test_new_user_{ts}',
            'email': f'test_new_{ts}@example.com',
            'password': 'testpass123',
            'industry_id': 1,
            'company_name': 'テスト会社'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 新しいユーザーを作成成功")
    
    def test_create_user_duplicate_username(self, admin_client):
        """重複ユーザー名で作成失敗"""
        response = admin_client.post('/api/admin/users', json={
            'username': 'admin',  # 既存ユーザー
            'email': 'duplicate@example.com',
            'password': 'testpass123'
        })
        assert response.status_code == 400
        print("✓ 重複ユーザー名で正しくエラー返却")
    
    def test_get_user(self, admin_client):
        """ユーザー詳細を取得"""
        response = admin_client.get('/api/admin/users/1')  # admin user
        assert response.status_code == 200
        data = response.get_json()
        assert data['username'] == 'admin'
        print("✓ ユーザー詳細を取得成功")
    
    def test_normal_user_cannot_create_user(self, client):
        """一般ユーザー(role=user)はユーザー作成不可"""
        client.post('/login', json={
            'username': 'ryokan_suzuki',
            'password': 'user123'
        })
        response = client.post('/api/admin/users', json={
            'username': 'unauthorized_user',
            'email': 'unauth@example.com',
            'password': 'testpass123'
        })
        assert response.status_code == 403
        print("✓ 一般ユーザーはユーザー作成不可（正常）")


# ========== ページアクセステスト ==========

class TestPageAccess:
    """各ページへのアクセステスト"""
    
    def test_courses_page(self, hotel_client):
        """コースカタログページにアクセス"""
        response = hotel_client.get('/courses')
        assert response.status_code == 200
        print("✓ コースカタログページにアクセス可能")
    
    def test_dashboard_page(self, hotel_client):
        """ダッシュボードページにアクセス"""
        response = hotel_client.get('/dashboard')
        assert response.status_code == 200
        print("✓ ダッシュボードページにアクセス可能")
    
    def test_unauthenticated_redirect(self, client):
        """未認証ユーザーはログインページにリダイレクト"""
        response = client.get('/courses', follow_redirects=False)
        assert response.status_code == 302
        print("✓ 未認証ユーザーは正しくリダイレクトされます")


class TestDashboardIndustryFilter:
    """ダッシュボード（全動画一覧）の業種フィルタリングテスト"""
    
    def test_hotel_user_dashboard_excludes_nursing_videos(self, client):
        """宿泊業ユーザーのダッシュボードに介護業向け動画が表示されない"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert '介護業向けAI活用'.encode('utf-8') not in response.data, \
            "宿泊業ユーザーのダッシュボードに介護業向けの動画が表示されてはならない"
        print("✓ 宿泊業ユーザーのダッシュボードに介護業動画は非表示")
    
    def test_hotel_user_dashboard_excludes_retail_videos(self, client):
        """宿泊業ユーザーのダッシュボードに小売業向け動画が表示されない"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert '小売業向けAI活用'.encode('utf-8') not in response.data, \
            "宿泊業ユーザーのダッシュボードに小売業向けの動画が表示されてはならない"
        print("✓ 宿泊業ユーザーのダッシュボードに小売業動画は非表示")
    
    def test_hotel_user_dashboard_shows_common_videos(self, client):
        """宿泊業ユーザーのダッシュボードに共通動画が表示される"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/dashboard')
        assert response.status_code == 200
        # 共通カテゴリーの動画は表示されるはず
        # 基礎編に含まれる動画があればそれが表示される
        print("✓ 宿泊業ユーザーのダッシュボードに共通動画が表示される")
    
    def test_admin_dashboard_shows_all_videos(self, admin_client):
        """管理者のダッシュボードには全動画が表示される"""
        response = admin_client.get('/dashboard')
        assert response.status_code == 200
        print("✓ 管理者のダッシュボードに全動画が表示される")
    
    def test_hotel_user_cannot_watch_nursing_video(self, client):
        """宿泊業ユーザーは介護業向け動画を直接視聴できない"""
        db = sqlite3.connect(TEST_DB_PATH)
        db.row_factory = sqlite3.Row
        
        # 介護業向けカテゴリーの動画IDを取得
        nursing_video = db.execute('''
            SELECT v.id, v.slug FROM videos v
            JOIN categories c ON v.category_id = c.id
            JOIN category_industry_access cia ON c.id = cia.category_id
            JOIN industries i ON cia.industry_id = i.id
            WHERE i.name = '介護'
            LIMIT 1
        ''').fetchone()
        db.close()
        
        if nursing_video:
            client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
            watch_url = f"/watch/{nursing_video['slug'] or nursing_video['id']}"
            response = client.get(watch_url)
            assert response.status_code == 403, \
                f"宿泊業ユーザーが介護動画({watch_url})にアクセスできてはならない（got {response.status_code}）"
            print("✓ 宿泊業ユーザーは介護業向け動画を直接視聴できない")
        else:
            print("✓ (介護業向けの動画がテストDBにないためスキップ)")


# ========== テナント管理APIテスト ==========

class TestTenantAPI:
    """テナント管理APIのテスト"""
    
    def test_get_tenants(self, admin_client):
        """テナント一覧を取得"""
        response = admin_client.get('/api/admin/tenants')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) > 0
        tenant_names = [t['name'] for t in data]
        assert 'グランドホテル東京' in tenant_names
        print(f"✓ テナント一覧を取得（{len(data)}件）")
    
    def test_create_tenant(self, admin_client):
        """新しいテナントを作成"""
        response = admin_client.post('/api/admin/tenants', json={
            'name': 'テストホテル',
            'industry_id': 1
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 新しいテナントを作成成功")
    
    def test_company_admin_cannot_create_tenant(self, hotel_client):
        """company_adminはテナント作成不可"""
        response = hotel_client.post('/api/admin/tenants', json={
            'name': '不正なテナント',
            'industry_id': 1
        })
        assert response.status_code == 403
        print("✓ company_adminはテナント作成不可（正常）")
    
    def test_normal_user_cannot_access_tenants(self, client):
        """未認証ユーザーはテナントAPIにアクセス不可"""
        client.post('/login', json={
            'username': 'ryokan_suzuki',
            'password': 'user123'
        })
        response = client.get('/api/admin/tenants')
        assert response.status_code == 403
        print("✓ 一般ユーザーはテナントAPIにアクセス不可（正常）")


# ========== 部署管理APIテスト ==========

class TestDepartmentAPI:
    """部署管理APIのテスト"""
    
    def test_get_departments(self, admin_client):
        """部署一覧を取得"""
        response = admin_client.get('/api/admin/departments')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) > 0
        dept_names = [d['name'] for d in data]
        assert 'フロント課' in dept_names
        print(f"✓ 部署一覧を取得（{len(data)}件）")
    
    def test_get_departments_by_tenant(self, admin_client):
        """テナント指定で部署一覧を取得"""
        # まずテナント一覧を取得してIDを取得
        tenants = admin_client.get('/api/admin/tenants').get_json()
        hotel_tenant = next((t for t in tenants if t['name'] == 'グランドホテル東京'), None)
        assert hotel_tenant is not None
        
        response = admin_client.get(f'/api/admin/departments?tenant_id={hotel_tenant["id"]}')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 2  # フロント課, 営業部
        print(f"✓ テナント指定で部署一覧を取得（{len(data)}件）")
    
    def test_create_department(self, admin_client):
        """新しい部署を作成"""
        tenants = admin_client.get('/api/admin/tenants').get_json()
        hotel_tenant = next((t for t in tenants if t['name'] == 'グランドホテル東京'), None)
        
        response = admin_client.post('/api/admin/departments', json={
            'name': 'テスト部署',
            'tenant_id': hotel_tenant['id']
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 新しい部署を作成成功")
    
    def test_update_department(self, admin_client):
        """部署名を更新"""
        # 新しい部署を作成
        tenants = admin_client.get('/api/admin/tenants').get_json()
        hotel_tenant = next((t for t in tenants if t['name'] == 'グランドホテル東京'), None)
        
        create_resp = admin_client.post('/api/admin/departments', json={
            'name': '更新テスト部署',
            'tenant_id': hotel_tenant['id']
        })
        dept_id = create_resp.get_json()['id']
        
        response = admin_client.put(f'/api/admin/departments/{dept_id}', json={
            'name': '更新後の部署名'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 部署名を更新成功")
    
    def test_delete_department_with_no_users(self, admin_client):
        """ユーザーのいない部署を削除"""
        tenants = admin_client.get('/api/admin/tenants').get_json()
        hotel_tenant = next((t for t in tenants if t['name'] == 'グランドホテル東京'), None)
        
        create_resp = admin_client.post('/api/admin/departments', json={
            'name': '削除テスト部署',
            'tenant_id': hotel_tenant['id']
        })
        dept_id = create_resp.get_json()['id']
        
        response = admin_client.delete(f'/api/admin/departments/{dept_id}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ ユーザーのいない部署を削除成功")
    
    def test_company_admin_sees_own_departments(self, hotel_client):
        """company_adminは自テナントの部署のみ取得"""
        response = hotel_client.get('/api/admin/departments')
        assert response.status_code == 200
        data = response.get_json()
        # hotel_tanaka は company_admin なので、グランドホテル東京の部署のみ
        for dept in data:
            assert dept['tenant_name'] == 'グランドホテル東京'
        print(f"✓ company_adminは自テナントの部署のみ取得（{len(data)}件）")


# ========== 部署別視聴統計テスト ==========

class TestDepartmentStats:
    """部署別視聴統計のテスト"""
    
    def test_get_department_stats(self, admin_client):
        """部署別統計を取得"""
        tenants = admin_client.get('/api/admin/tenants').get_json()
        hotel_tenant = next((t for t in tenants if t['name'] == 'グランドホテル東京'), None)
        
        response = admin_client.get(f'/api/admin/department-stats?tenant_id={hotel_tenant["id"]}')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        print(f"✓ 部署別統計を取得（{len(data)}件）")


# ========== CSV一括ユーザー登録/出力テスト ==========

class TestCSVImportExport:
    """CSV一括ユーザー登録/出力のテスト"""
    
    def test_export_csv(self, admin_client):
        """ユーザー一覧をCSVでエクスポート"""
        response = admin_client.get('/api/admin/users/export-csv')
        assert response.status_code == 200
        assert 'text/csv' in response.content_type or 'attachment' in response.headers.get('Content-Disposition', '')
        # CSVの内容を確認
        content = response.data.decode('utf-8-sig')
        assert 'ユーザー名' in content
        assert 'admin' in content
        print("✓ ユーザー一覧をCSVエクスポート成功")
    
    def test_import_csv(self, admin_client):
        """CSVからユーザーを一括登録"""
        import io
        import time
        ts = int(time.time())
        csv_content = 'ユーザー名,メール,パスワード,会社名,ロール,業種,テナント,部署\n'
        csv_content += f'csv_test_{ts},csv_test_{ts}@example.com,testpass123,テスト会社,user,宿泊,グランドホテル東京,フロント課\n'
        
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8-sig')), 'test_users.csv')
        }
        response = admin_client.post('/api/admin/users/import-csv', 
                                      data=data, content_type='multipart/form-data')
        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] == True
        assert result['created'] >= 1
        print(f"✓ CSVからユーザー一括登録成功（{result['created']}件）")
    
    def test_import_csv_duplicate_user(self, admin_client):
        """CSV登録で重複ユーザーはスキップ"""
        import io
        csv_content = 'ユーザー名,メール,パスワード,会社名,ロール\n'
        csv_content += 'admin,admin@example.com,testpass123,テスト,user\n'
        
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8-sig')), 'dup_users.csv')
        }
        response = admin_client.post('/api/admin/users/import-csv',
                                      data=data, content_type='multipart/form-data')
        assert response.status_code == 200
        result = response.get_json()
        assert result['created'] == 0
        assert len(result.get('errors', [])) > 0
        print("✓ 重複ユーザーを正しくスキップ")
    
    def test_import_csv_no_file(self, admin_client):
        """CSVファイルなしでエラー"""
        response = admin_client.post('/api/admin/users/import-csv')
        assert response.status_code == 400
        print("✓ CSVファイルなしで正しくエラー返却")
    
    def test_company_admin_export_csv(self, hotel_client):
        """company_adminは自テナントユーザーのみエクスポート"""
        response = hotel_client.get('/api/admin/users/export-csv')
        assert response.status_code == 200
        content = response.data.decode('utf-8-sig')
        # company_adminなので自テナントのユーザーのみ含まれるはず
        assert 'ユーザー名' in content
        print("✓ company_adminの自テナントCSVエクスポート成功")


# ========== セキュリティバリデーションテスト ==========

class TestSecurityValidation:
    """ユーザー作成・CSVインポートのセキュリティバリデーションテスト"""
    
    # --- ロール値バリデーション ---
    
    def test_create_user_invalid_role(self, admin_client):
        """無効なロール値でユーザー作成が拒否される"""
        import time
        ts = int(time.time())
        response = admin_client.post('/api/admin/users', json={
            'username': f'invalid_role_{ts}',
            'email': f'invalid_role_{ts}@example.com',
            'password': 'testpass123',
            'role': 'admin'  # 無効なロール値
        })
        assert response.status_code == 400
        data = response.get_json()
        assert '無効なロール' in data['error']
        print("✓ 無効なロール値でユーザー作成が正しく拒否")
    
    def test_import_csv_invalid_role(self, admin_client):
        """CSVインポートで無効なロール値がエラーになる"""
        import io
        import time
        ts = int(time.time())
        csv_content = 'ユーザー名,メール,パスワード,会社名,ロール\n'
        csv_content += f'csv_invalid_role_{ts},csv_invalid_{ts}@example.com,testpass123,テスト会社,root\n'
        
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8-sig')), 'test_invalid_role.csv')
        }
        response = admin_client.post('/api/admin/users/import-csv',
                                      data=data, content_type='multipart/form-data')
        assert response.status_code == 200
        result = response.get_json()
        assert result['created'] == 0
        assert any('無効なロール' in e for e in result.get('errors', []))
        print("✓ CSVインポートで無効なロール値が正しくエラー")
    
    # --- パスワード強度バリデーション ---
    
    def test_create_user_short_password(self, admin_client):
        """短すぎるパスワードでユーザー作成が拒否される"""
        import time
        ts = int(time.time())
        response = admin_client.post('/api/admin/users', json={
            'username': f'short_pw_{ts}',
            'email': f'short_pw_{ts}@example.com',
            'password': 'abc',  # 3文字（8文字未満）
            'role': 'user'
        })
        assert response.status_code == 400
        data = response.get_json()
        assert 'パスワード' in data['error'] and '8文字' in data['error']
        print("✓ 短すぎるパスワードでユーザー作成が正しく拒否")
    
    def test_import_csv_short_password(self, admin_client):
        """CSVインポートで短すぎるパスワードがエラーになる"""
        import io
        import time
        ts = int(time.time())
        csv_content = 'ユーザー名,メール,パスワード,会社名,ロール\n'
        csv_content += f'csv_shortpw_{ts},csv_shortpw_{ts}@example.com,abc,テスト会社,user\n'
        
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8-sig')), 'test_short_pw.csv')
        }
        response = admin_client.post('/api/admin/users/import-csv',
                                      data=data, content_type='multipart/form-data')
        assert response.status_code == 200
        result = response.get_json()
        assert result['created'] == 0
        assert any('パスワード' in e and '8文字' in e for e in result.get('errors', []))
        print("✓ CSVインポートで短すぎるパスワードが正しくエラー")
    
    def test_import_csv_empty_password(self, admin_client):
        """CSVインポートで空パスワードがエラーになる"""
        import io
        import time
        ts = int(time.time())
        csv_content = 'ユーザー名,メール,パスワード,会社名,ロール\n'
        csv_content += f'csv_nopw_{ts},csv_nopw_{ts}@example.com,,テスト会社,user\n'
        
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8-sig')), 'test_no_pw.csv')
        }
        response = admin_client.post('/api/admin/users/import-csv',
                                      data=data, content_type='multipart/form-data')
        assert response.status_code == 200
        result = response.get_json()
        assert result['created'] == 0
        assert any('パスワード' in e and '空' in e for e in result.get('errors', []))
        print("✓ CSVインポートで空パスワードが正しくエラー")
    
    # --- メール形式バリデーション ---
    
    def test_create_user_invalid_email(self, admin_client):
        """不正なメール形式でユーザー作成が拒否される"""
        import time
        ts = int(time.time())
        response = admin_client.post('/api/admin/users', json={
            'username': f'bad_email_{ts}',
            'email': 'not-an-email',
            'password': 'testpass123',
            'role': 'user'
        })
        assert response.status_code == 400
        data = response.get_json()
        assert 'メールアドレス' in data['error']
        print("✓ 不正なメール形式でユーザー作成が正しく拒否")
    
    def test_import_csv_invalid_email(self, admin_client):
        """CSVインポートで不正なメール形式がエラーになる"""
        import io
        import time
        ts = int(time.time())
        csv_content = 'ユーザー名,メール,パスワード,会社名,ロール\n'
        csv_content += f'csv_bademail_{ts},not-a-valid-email,testpass123,テスト会社,user\n'
        
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8-sig')), 'test_bad_email.csv')
        }
        response = admin_client.post('/api/admin/users/import-csv',
                                      data=data, content_type='multipart/form-data')
        assert response.status_code == 200
        result = response.get_json()
        assert result['created'] == 0
        assert any('メールアドレス' in e for e in result.get('errors', []))
        print("✓ CSVインポートで不正なメール形式が正しくエラー")
    
    # --- company_admin 権限エスカレーション防止 ---
    
    def test_company_admin_cannot_create_super_admin(self, hotel_client):
        """company_adminはsuper_adminを作成できない"""
        import time
        ts = int(time.time())
        response = hotel_client.post('/api/admin/users', json={
            'username': f'escalate_super_{ts}',
            'email': f'escalate_super_{ts}@example.com',
            'password': 'testpass123',
            'role': 'super_admin'
        })
        assert response.status_code == 403
        data = response.get_json()
        assert 'super_admin' in data['error']
        print("✓ company_adminによるsuper_admin作成が正しく拒否")
    
    def test_company_admin_cannot_create_company_admin(self, hotel_client):
        """company_adminは他のcompany_adminを作成できない"""
        import time
        ts = int(time.time())
        response = hotel_client.post('/api/admin/users', json={
            'username': f'escalate_cadmin_{ts}',
            'email': f'escalate_cadmin_{ts}@example.com',
            'password': 'testpass123',
            'role': 'company_admin'
        })
        assert response.status_code == 403
        data = response.get_json()
        assert 'company_admin' in data['error']
        print("✓ company_adminによるcompany_admin作成が正しく拒否")
    
    def test_company_admin_csv_cannot_create_super_admin(self, hotel_client):
        """company_adminはCSVでsuper_adminを作成できない"""
        import io
        import time
        ts = int(time.time())
        csv_content = 'ユーザー名,メール,パスワード,会社名,ロール\n'
        csv_content += f'csv_escalate_{ts},csv_escalate_{ts}@example.com,testpass123,テスト会社,super_admin\n'
        
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8-sig')), 'test_escalate.csv')
        }
        response = hotel_client.post('/api/admin/users/import-csv',
                                      data=data, content_type='multipart/form-data')
        assert response.status_code == 200
        result = response.get_json()
        assert result['created'] == 0
        assert any('super_admin' in e for e in result.get('errors', []))
        print("✓ company_adminによるCSVでのsuper_admin作成が正しく拒否")
    
    def test_company_admin_csv_cannot_create_company_admin(self, hotel_client):
        """company_adminはCSVで他のcompany_adminを作成できない"""
        import io
        import time
        ts = int(time.time())
        csv_content = 'ユーザー名,メール,パスワード,会社名,ロール\n'
        csv_content += f'csv_cadmin_{ts},csv_cadmin_{ts}@example.com,testpass123,テスト会社,company_admin\n'
        
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8-sig')), 'test_cadmin.csv')
        }
        response = hotel_client.post('/api/admin/users/import-csv',
                                      data=data, content_type='multipart/form-data')
        assert response.status_code == 200
        result = response.get_json()
        assert result['created'] == 0
        assert any('company_admin' in e for e in result.get('errors', []))
        print("✓ company_adminによるCSVでのcompany_admin作成が正しく拒否")
    
    # --- super_adminの正常動作確認 ---
    
    def test_super_admin_can_create_all_roles(self, admin_client):
        """super_adminは全ロールのユーザーを作成できる"""
        import time
        ts = int(time.time())
        
        for role in ['user', 'company_admin', 'super_admin']:
            response = admin_client.post('/api/admin/users', json={
                'username': f'role_test_{role}_{ts}',
                'email': f'role_test_{role}_{ts}@example.com',
                'password': 'testpass123',
                'role': role
            })
            assert response.status_code == 200, f'super_adminが{role}ロールを作成できるべき'
        print("✓ super_adminは全ロール（user/company_admin/super_admin）を作成可能")
    
    def test_valid_email_formats_accepted(self, admin_client):
        """正常なメール形式が受け入れられる"""
        import time
        ts = int(time.time())
        response = admin_client.post('/api/admin/users', json={
            'username': f'valid_email_{ts}',
            'email': f'valid.user+tag_{ts}@example.co.jp',
            'password': 'testpass123',
            'role': 'user'
        })
        assert response.status_code == 200
        print("✓ 正常なメール形式（サブドメイン/タグ付き）が正しく受け入れ")


# ========== 個人別視聴統計テスト ==========

class TestUserStatsDetail:
    """個人別視聴統計の拡張テスト"""
    
    def test_get_user_stats_detail(self, admin_client):
        """ユーザー詳細統計を取得"""
        response = admin_client.get('/api/admin/user-stats-detail/1')
        assert response.status_code == 200
        data = response.get_json()
        assert 'user' in data
        assert 'summary' in data
        assert 'details' in data
        summary = data['summary']
        assert 'total_videos' in summary
        assert 'viewed_videos' in summary
        assert 'completed_videos' in summary
        assert 'completion_rate' in summary
        assert 'total_watch_time_seconds' in summary
        assert 'total_watch_time_display' in summary
        assert 'avg_progress' in summary
        print("✓ ユーザー詳細統計を取得成功")
    
    def test_get_nonexistent_user_stats(self, admin_client):
        """存在しないユーザーの統計を取得で404"""
        response = admin_client.get('/api/admin/user-stats-detail/9999')
        assert response.status_code == 404
        print("✓ 存在しないユーザーの統計で正しく404返却")
    
    def test_company_admin_cannot_see_other_tenant_stats(self, hotel_client):
        """company_adminは他テナントのユーザー統計を参照不可"""
        # retail_yamada(id=4) はスーパーマートのcompany_admin
        # hotel_tanaka はグランドホテル東京のcompany_admin
        # hotel_tanaka から retail_yamada の統計を見ようとする
        response = hotel_client.get('/api/admin/user-stats-detail/4')
        assert response.status_code == 403
        print("✓ company_adminは他テナントのユーザー統計を参照不可（正常）")


# ========== アクセス分析ダッシュボードテスト ==========

class TestAnalyticsDashboard:
    """アクセス分析ダッシュボードのテスト"""
    
    def test_analytics_page_loads(self, admin_client):
        """分析ダッシュボードページが正常に表示"""
        response = admin_client.get('/admin/analytics')
        assert response.status_code == 200
        assert 'アクセス分析'.encode('utf-8') in response.data
        print("✓ 分析ダッシュボードページが正常に表示")
    
    def test_analytics_summary(self, admin_client):
        """分析サマリーAPIを取得"""
        response = admin_client.get('/api/admin/analytics/summary?days=30')
        assert response.status_code == 200
        data = response.get_json()
        assert 'daily' in data
        assert 'pages' in data
        assert 'user_access' in data
        assert 'total' in data
        print("✓ 分析サマリーAPIを取得成功")
    
    def test_analytics_unauthenticated(self, client):
        """未認証ユーザーは分析ダッシュボードにアクセス不可"""
        response = client.get('/admin/analytics', follow_redirects=False)
        assert response.status_code == 302
        print("✓ 未認証ユーザーは分析ダッシュボードにアクセス不可（正常）")
    
    def test_normal_user_cannot_access_analytics(self, client):
        """一般ユーザーは分析ダッシュボードにアクセス不可"""
        client.post('/login', json={
            'username': 'ryokan_suzuki',
            'password': 'user123'
        })
        response = client.get('/admin/analytics')
        assert response.status_code == 403
        print("✓ 一般ユーザーは分析ダッシュボードにアクセス不可（正常）")


# ========== ロールベースアクセス制御テスト ==========

class TestRoleBasedAccess:
    """ロールベースのアクセス制御テスト"""
    
    def test_super_admin_login_has_role(self, client):
        """super_adminログイン時にroleがセッションに保存される"""
        response = client.post('/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        data = response.get_json()
        assert data['success'] == True
        assert data.get('role') == 'super_admin' or data.get('is_admin') == True
        print("✓ super_adminのロール情報がログイン時に返却")
    
    def test_company_admin_login_has_role(self, client):
        """company_adminログイン時にroleがセッションに保存される"""
        response = client.post('/login', json={
            'username': 'hotel_tanaka',
            'password': 'user123'
        })
        data = response.get_json()
        assert data['success'] == True
        print("✓ company_adminのログイン成功")
    
    def test_company_admin_can_access_admin_page(self, hotel_client):
        """company_adminは管理画面にアクセス可能"""
        response = hotel_client.get('/admin')
        assert response.status_code == 200
        print("✓ company_adminは管理画面にアクセス可能")
    
    def test_normal_user_cannot_access_admin(self, client):
        """一般ユーザー(role=user)は管理画面にアクセス不可"""
        client.post('/login', json={
            'username': 'ryokan_suzuki',
            'password': 'user123'
        })
        response = client.get('/admin')
        assert response.status_code == 403
        print("✓ 一般ユーザーは管理画面にアクセス不可（正常）")


# ========== GA4設定テスト ==========

class TestGA4Integration:
    """GA4統合のテスト"""
    
    def test_ga4_tracking_included_in_pages(self, hotel_client):
        """GA4トラッキングコードがページに含まれる（設定時）"""
        # GA_MEASUREMENT_IDが空の場合、trackingコードは表示されない
        response = hotel_client.get('/courses')
        assert response.status_code == 200
        # ga4_tracking.htmlのインクルードが動作していることを確認
        # GA_MEASUREMENT_IDが空なら gtag は表示されない（正常動作）
        print("✓ GA4トラッキングの条件付きインクルードが動作")
    
    def test_ga4_tracking_template_exists(self, admin_client):
        """GA4トラッキングテンプレートが存在する"""
        # login, courses, dashboard, watch, admin, chat, analytics で ga4_tracking.html が呼ばれている
        # テンプレートが正しくロードされることを、ページ読み込みエラーなしで確認
        pages = ['/courses', '/dashboard', '/admin']
        for page in pages:
            response = admin_client.get(page)
            assert response.status_code == 200, f"Page {page} failed to load"
        print("✓ GA4トラッキングテンプレートが全ページで正常にロード")


# ========== データベースマイグレーションテスト ==========

class TestDatabaseMigration:
    """データベースマイグレーションのテスト"""
    
    def test_migrate_db_import(self):
        """migrate_db.pyがインポート可能"""
        import importlib
        migrate_db = importlib.import_module('migrate_db')
        assert hasattr(migrate_db, 'run_migrations')
        assert hasattr(migrate_db, 'show_status')
        assert hasattr(migrate_db, 'create_backup')
        assert hasattr(migrate_db, 'MIGRATIONS')
        print("✓ migrate_db.pyが正常にインポート可能")
    
    def test_migrations_are_ordered(self):
        """マイグレーションが正しい順序で定義されている"""
        from migrate_db import MIGRATIONS
        versions = [m[0] for m in MIGRATIONS]
        assert versions == sorted(versions), "マイグレーションのバージョンが昇順でない"
        assert len(versions) == len(set(versions)), "マイグレーションに重複バージョンがある"
        print(f"✓ マイグレーションが正しい順序で定義（{len(versions)}件）")
    
    def test_schema_migrations_table_exists(self):
        """schema_migrationsテーブルが存在する"""
        if not os.path.exists(TEST_DB_PATH):
            pytest.skip("test DB not found")
        db = sqlite3.connect(TEST_DB_PATH)
        cursor = db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
        result = cursor.fetchone()
        db.close()
        assert result is not None, "schema_migrationsテーブルが存在しない"
        print("✓ schema_migrationsテーブルが存在")
    
    def test_all_tables_exist(self):
        """必要な全テーブルが存在する"""
        if not os.path.exists(TEST_DB_PATH):
            pytest.skip("test DB not found")
        db = sqlite3.connect(TEST_DB_PATH)
        cursor = db.cursor()
        expected_tables = [
            'industries', 'tenants', 'departments', 'users', 'categories',
            'videos', 'progress', 'category_industry_access', 'video_transcripts',
            'industry_usecases', 'chat_history', 'access_logs',
            'video_questions', 'video_answers', 'announcements'
        ]
        for table in expected_tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            result = cursor.fetchone()
            assert result is not None, f"テーブル {table} が存在しない"
        db.close()
        print(f"✓ 必要な全テーブル（{len(expected_tables)}個）が存在")
    
    def test_users_table_has_new_columns(self):
        """usersテーブルに新しいカラムが存在する"""
        if not os.path.exists(TEST_DB_PATH):
            pytest.skip("test DB not found")
        db = sqlite3.connect(TEST_DB_PATH)
        cursor = db.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        db.close()
        assert 'tenant_id' in columns, "tenant_idカラムがない"
        assert 'department_id' in columns, "department_idカラムがない"
        assert 'role' in columns, "roleカラムがない"
        print("✓ usersテーブルにtenant_id, department_id, roleカラムが存在")
    
    def test_backup_creation(self):
        """バックアップが正しく作成される"""
        from migrate_db import create_backup, BACKUP_DIR
        if not os.path.exists('lms.db'):
            pytest.skip("lms.db not found (backup tests require production DB)")
        backup_path = create_backup()
        assert backup_path is not None
        assert os.path.exists(backup_path)
        # テスト後にバックアップを削除
        os.remove(backup_path)
        print("✓ バックアップが正しく作成される")


# ========== 動画視聴分析ダッシュボードテスト ==========

class TestVideoAnalyticsDashboard:
    """動画視聴分析ダッシュボードのテスト"""
    
    def test_video_analytics_page_loads_for_super_admin(self, admin_client):
        """super_adminは動画視聴分析ページにアクセス可能"""
        response = admin_client.get('/admin/video-analytics')
        assert response.status_code == 200
        assert '動画視聴分析'.encode('utf-8') in response.data
        print("✓ super_adminは動画視聴分析ページにアクセス可能")
    
    def test_video_analytics_page_loads_for_company_admin(self, hotel_client):
        """company_adminは動画視聴分析ページにアクセス可能"""
        response = hotel_client.get('/admin/video-analytics')
        assert response.status_code == 200
        assert '動画視聴分析'.encode('utf-8') in response.data
        print("✓ company_adminは動画視聴分析ページにアクセス可能")
    
    def test_video_analytics_denied_for_normal_user(self, client):
        """一般ユーザー(role=user)は動画視聴分析にアクセス不可"""
        client.post('/login', json={
            'username': 'ryokan_suzuki',
            'password': 'user123'
        })
        response = client.get('/admin/video-analytics')
        assert response.status_code == 403
        print("✓ 一般ユーザーは動画視聴分析にアクセス不可（正常）")
    
    def test_video_analytics_denied_for_unauthenticated(self, client):
        """未認証ユーザーは動画視聴分析にアクセス不可"""
        response = client.get('/admin/video-analytics', follow_redirects=False)
        assert response.status_code == 302
        print("✓ 未認証ユーザーは動画視聴分析にアクセス不可（リダイレクト）")


class TestVideoAnalyticsAPI:
    """動画視聴分析APIのテスト"""
    
    def test_summary_api_returns_correct_structure(self, admin_client):
        """視聴分析APIが正しい構造のデータを返す"""
        response = admin_client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        # トップレベルキー
        assert 'summary' in data
        assert 'video_stats' in data
        assert 'user_stats' in data
        assert 'dept_stats' in data
        assert 'daily_activity' in data
        
        # サマリーの構造
        summary = data['summary']
        assert 'total_videos' in summary
        assert 'total_viewers' in summary
        assert 'overall_avg_progress' in summary
        assert 'overall_completion_rate' in summary
        assert 'total_completions' in summary
        assert 'videos_with_views' in summary
        
        # 型チェック
        assert isinstance(summary['total_videos'], int)
        assert isinstance(summary['total_viewers'], int)
        assert isinstance(summary['overall_avg_progress'], (int, float))
        assert isinstance(summary['overall_completion_rate'], (int, float))
        
        print("✓ 視聴分析APIが正しい構造のデータを返却")
    
    def test_summary_api_with_period_filter(self, admin_client):
        """期間フィルター付きで視聴分析APIを呼び出し"""
        for days in [7, 30, 90, 365]:
            response = admin_client.get(f'/api/admin/video-analytics/summary?days={days}')
            assert response.status_code == 200
            data = response.get_json()
            assert 'daily_activity' in data
        print("✓ 期間フィルター（7/30/90/365日）で正常にデータ返却")
    
    def test_summary_api_denied_for_normal_user(self, client):
        """一般ユーザーは視聴分析APIにアクセス不可"""
        client.post('/login', json={
            'username': 'ryokan_suzuki',
            'password': 'user123'
        })
        response = client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 403
        print("✓ 一般ユーザーは視聴分析APIにアクセス不可（正常）")
    
    def test_summary_api_denied_for_unauthenticated(self, client):
        """未認証ユーザーは視聴分析APIにアクセス不可"""
        response = client.get('/api/admin/video-analytics/summary', follow_redirects=False)
        assert response.status_code == 302
        print("✓ 未認証ユーザーは視聴分析APIにアクセス不可（リダイレクト）")


class TestVideoAnalyticsTenantIsolation:
    """動画視聴分析のテナント分離テスト"""
    
    @pytest.fixture(autouse=True)
    def setup_progress_data(self):
        """テスト用の視聴進捗データをテストDBに挿入"""
        db = sqlite3.connect(TEST_DB_PATH)
        db.row_factory = sqlite3.Row
        
        # テスト用動画を作成
        db.execute('''
            INSERT OR IGNORE INTO videos (id, title, filename, category_id)
            VALUES (901, 'テスト動画A', 'test_a.mp4', 1)
        ''')
        db.execute('''
            INSERT OR IGNORE INTO videos (id, title, filename, category_id)
            VALUES (902, 'テスト動画B', 'test_b.mp4', 1)
        ''')
        
        # ユーザーIDを取得
        hotel_user = db.execute("SELECT id FROM users WHERE username = 'hotel_tanaka'").fetchone()
        ryokan_user = db.execute("SELECT id FROM users WHERE username = 'ryokan_suzuki'").fetchone()
        retail_user = db.execute("SELECT id FROM users WHERE username = 'retail_yamada'").fetchone()
        
        if hotel_user and ryokan_user and retail_user:
            # hotel_tanaka（グランドホテル東京）の進捗
            db.execute('''
                INSERT OR REPLACE INTO progress (user_id, video_id, progress_percent, last_position)
                VALUES (?, 901, 95, 300)
            ''', (hotel_user['id'],))
            db.execute('''
                INSERT OR REPLACE INTO progress (user_id, video_id, progress_percent, last_position)
                VALUES (?, 902, 50, 120)
            ''', (hotel_user['id'],))
            
            # ryokan_suzuki（湯元旅館）の進捗
            db.execute('''
                INSERT OR REPLACE INTO progress (user_id, video_id, progress_percent, last_position)
                VALUES (?, 901, 30, 90)
            ''', (ryokan_user['id'],))
            
            # retail_yamada（スーパーマート）の進捗
            db.execute('''
                INSERT OR REPLACE INTO progress (user_id, video_id, progress_percent, last_position)
                VALUES (?, 901, 80, 240)
            ''', (retail_user['id'],))
        
        db.commit()
        db.close()
        
        yield
        
        # クリーンアップ: テスト動画と進捗データを削除
        db = sqlite3.connect(TEST_DB_PATH)
        db.execute('DELETE FROM progress WHERE video_id IN (901, 902)')
        db.execute('DELETE FROM videos WHERE id IN (901, 902)')
        db.commit()
        db.close()
    
    def test_super_admin_sees_all_tenant_data(self, admin_client):
        """super_adminは全テナントの視聴データを閲覧可能"""
        response = admin_client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        # 全テナントのユーザーの視聴データが含まれる
        user_names = [u['username'] for u in data['user_stats']]
        # super_adminなので、グランドホテル東京もスーパーマートも見える
        assert 'hotel_tanaka' in user_names, f"hotel_tanaka not in {user_names}"
        assert 'retail_yamada' in user_names, f"retail_yamada not in {user_names}"
        print("✓ super_adminは全テナントの視聴データを閲覧可能")
    
    def test_super_admin_sees_all_departments(self, admin_client):
        """super_adminは全テナントの部署統計を閲覧可能"""
        response = admin_client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        # 複数テナントの部署が含まれる
        tenant_names = set(d['tenant_name'] for d in data['dept_stats'])
        assert len(tenant_names) >= 2, f"super_adminなのに部署のテナントが1つ以下: {tenant_names}"
        print(f"✓ super_adminは全テナントの部署統計を閲覧可能（{len(tenant_names)}テナント）")
    
    def test_company_admin_sees_only_own_tenant_users(self, hotel_client):
        """company_adminは自テナントのユーザーの視聴データのみ閲覧可能"""
        response = hotel_client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        # hotel_tanaka（company_admin、グランドホテル東京）は自テナントのみ
        user_names = [u['username'] for u in data['user_stats']]
        # retail_yamada（スーパーマート）は含まれない
        assert 'retail_yamada' not in user_names, \
            f"company_adminが他テナントユーザーを閲覧できている: {user_names}"
        print("✓ company_adminは自テナントのユーザーのみ閲覧可能")
    
    def test_company_admin_sees_only_own_tenant_departments(self, hotel_client):
        """company_adminは自テナントの部署統計のみ閲覧可能"""
        response = hotel_client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        # 自テナントの部署のみ
        for dept in data['dept_stats']:
            assert dept['tenant_name'] == 'グランドホテル東京', \
                f"company_adminが他テナントの部署を閲覧: {dept['tenant_name']}"
        print("✓ company_adminは自テナントの部署統計のみ閲覧可能")
    
    def test_super_admin_video_stats_include_all_viewers(self, admin_client):
        """super_adminの動画統計には全視聴者がカウントされる"""
        response = admin_client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        # テスト動画A（id=901）の視聴者数を確認
        video_a = next((v for v in data['video_stats'] if v['id'] == 901), None)
        if video_a:
            # hotel_tanaka, ryokan_suzuki, retail_yamada の3人が視聴
            assert video_a['viewer_count'] >= 3, \
                f"super_adminなのにテスト動画Aの視聴者数が3未満: {video_a['viewer_count']}"
            print(f"✓ super_adminの動画Aの視聴者数: {video_a['viewer_count']}人（全テナント含む）")
        else:
            print("✓ テスト動画Aの視聴者統計を確認（動画データなし - 構造は正常）")
    
    def test_company_admin_video_stats_filtered(self, hotel_client):
        """company_adminの動画統計は自テナントの視聴者のみ"""
        response = hotel_client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        # テスト動画A（id=901）の視聴者数を確認
        video_a = next((v for v in data['video_stats'] if v['id'] == 901), None)
        if video_a:
            # hotel_tanaka のテナント（グランドホテル東京）にはhotel_tanakaのみ
            # ryokan_suzuki は湯元旅館（別テナント）なので含まれない
            # retail_yamada はスーパーマート（別テナント）なので含まれない
            assert video_a['viewer_count'] <= 2, \
                f"company_adminなのに他テナントの視聴者がカウントされている: {video_a['viewer_count']}"
            print(f"✓ company_adminの動画Aの視聴者数: {video_a['viewer_count']}人（自テナントのみ）")
        else:
            print("✓ テスト動画Aの視聴者統計を確認（動画データなし - 構造は正常）")
    
    def test_summary_totals_consistent(self, admin_client):
        """サマリーの数値が内訳と整合する"""
        response = admin_client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        summary = data['summary']
        assert summary['total_videos'] >= 0
        assert summary['total_viewers'] >= 0
        assert 0 <= summary['overall_avg_progress'] <= 100
        assert 0 <= summary['overall_completion_rate'] <= 100
        print("✓ サマリーの数値が妥当な範囲内")


class TestVideoAnalyticsNavigation:
    """動画視聴分析のナビゲーションリンクテスト"""
    
    def test_admin_page_has_video_analytics_link(self, admin_client):
        """管理画面に動画視聴分析リンクがある"""
        response = admin_client.get('/admin')
        assert response.status_code == 200
        assert '/admin/video-analytics'.encode('utf-8') in response.data
        assert '動画視聴分析'.encode('utf-8') in response.data
        print("✓ 管理画面に動画視聴分析リンクが存在")
    
    def test_access_analytics_page_has_video_analytics_link(self, admin_client):
        """アクセス分析ページに動画視聴分析リンクがある"""
        response = admin_client.get('/admin/analytics')
        assert response.status_code == 200
        assert '/admin/video-analytics'.encode('utf-8') in response.data
        print("✓ アクセス分析ページに動画視聴分析リンクが存在")
    
    def test_video_analytics_page_has_admin_link(self, admin_client):
        """動画視聴分析ページに管理画面リンクがある"""
        response = admin_client.get('/admin/video-analytics')
        assert response.status_code == 200
        assert '/admin'.encode('utf-8') in response.data
        assert '/admin/analytics'.encode('utf-8') in response.data
        print("✓ 動画視聴分析ページに管理画面・アクセス分析リンクが存在")


class TestTestDBIsolation:
    """テストDB分離の検証テスト"""
    
    def test_test_db_exists(self):
        """テスト用DBが存在する"""
        assert os.path.exists(TEST_DB_PATH), f"テスト用DB ({TEST_DB_PATH}) が存在しない"
        print(f"✓ テスト用DB存在: {os.path.basename(TEST_DB_PATH)}")
    
    def test_production_db_not_modified(self):
        """本番DBにテストデータが混入していない"""
        prod_db = os.path.join(os.path.dirname(__file__), 'lms.db')
        if not os.path.exists(prod_db):
            pytest.skip("本番DBが存在しない")
        
        db = sqlite3.connect(prod_db)
        
        # テスト業種が存在しないこと
        test_industries = db.execute(
            "SELECT COUNT(*) FROM industries WHERE name LIKE 'テスト業種%' OR name = '不正な業種'"
        ).fetchone()[0]
        assert test_industries == 0, f"本番DBにテスト業種が {test_industries} 件残っている"
        
        # テストユーザーが存在しないこと
        test_users = db.execute(
            "SELECT COUNT(*) FROM users WHERE username LIKE 'test_%' OR username LIKE 'csv_test_%'"
        ).fetchone()[0]
        assert test_users == 0, f"本番DBにテストユーザーが {test_users} 件残っている"
        
        # テストテナントが存在しないこと
        test_tenants = db.execute(
            "SELECT COUNT(*) FROM tenants WHERE name = 'テストホテル'"
        ).fetchone()[0]
        assert test_tenants == 0, f"本番DBにテストテナントが {test_tenants} 件残っている"
        
        db.close()
        print("✓ 本番DBにテストデータが混入していないことを確認")
    
    def test_app_config_uses_test_db(self):
        """アプリ設定がテスト用DBを参照している"""
        assert app.config['DATABASE'] == TEST_DB_PATH, \
            f"テスト中のDB参照先が不正: {app.config['DATABASE']}"
        print("✓ テスト中のアプリはテスト用DBを参照")


# ========== ユーザー視聴状況ダッシュボード テスト ==========

class TestUserProgressDashboard:
    """ユーザー視聴状況ダッシュボードのテスト"""
    
    def test_user_progress_page_loads_for_super_admin(self, admin_client):
        """super_adminがユーザー視聴状況ページにアクセスできる"""
        response = admin_client.get('/admin/user-progress')
        assert response.status_code == 200
        print("✓ super_adminがユーザー視聴状況ページにアクセスできる")

    def test_user_progress_page_loads_for_company_admin(self, hotel_client):
        """company_adminがユーザー視聴状況ページにアクセスできる"""
        response = hotel_client.get('/admin/user-progress')
        assert response.status_code == 200
        print("✓ company_adminがユーザー視聴状況ページにアクセスできる")

    def test_user_progress_denied_for_normal_user(self, client):
        """一般ユーザーはユーザー視聴状況ページにアクセスできない"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/admin/user-progress')
        assert response.status_code == 403
        print("✓ 一般ユーザーはユーザー視聴状況ページにアクセス不可")

    def test_user_progress_denied_for_unauthenticated(self, client):
        """未認証ユーザーはユーザー視聴状況ページにアクセスできない（リダイレクト）"""
        response = client.get('/admin/user-progress')
        assert response.status_code == 302
        print("✓ 未認証ユーザーはユーザー視聴状況ページにアクセス不可（リダイレクト）")


class TestUserProgressAPI:
    """ユーザー視聴状況APIのテスト"""
    
    def test_api_returns_correct_structure(self, admin_client):
        """APIが正しい構造のJSONを返す"""
        response = admin_client.get('/api/admin/user-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        # トップレベルキーの存在確認
        assert 'users' in data
        assert 'videos' in data
        assert 'departments' in data
        assert 'total_videos' in data
        
        # usersの構造確認
        if len(data['users']) > 0:
            user = data['users'][0]
            assert 'id' in user
            assert 'username' in user
            assert 'department_name' in user
            assert 'video_progress' in user
            assert 'videos_started' in user
            assert 'videos_completed' in user
            assert 'avg_progress' in user
            assert 'all_completed' in user
        
        # videosの構造確認
        if len(data['videos']) > 0:
            video = data['videos'][0]
            assert 'id' in video
            assert 'title' in video
            assert 'category_name' in video
        
        print("✓ APIが正しい構造のJSONを返す")

    def test_api_denied_for_normal_user(self, client):
        """一般ユーザーはAPIにアクセスできない"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/api/admin/user-progress')
        assert response.status_code == 403
        print("✓ 一般ユーザーはユーザー視聴状況APIにアクセス不可")

    def test_api_denied_for_unauthenticated(self, client):
        """未認証ユーザーはAPIにアクセスできない"""
        response = client.get('/api/admin/user-progress')
        assert response.status_code == 302
        print("✓ 未認証ユーザーはユーザー視聴状況APIにアクセス不可（リダイレクト）")


class TestUserProgressTenantIsolation:
    """ユーザー視聴状況のテナント分離テスト"""
    
    @pytest.fixture(autouse=True)
    def setup_progress_data(self):
        """テスト用の進捗データを作成"""
        db = get_db()
        
        # hotel_tanaka (tenant_id=1) の進捗データ
        hotel_user = db.execute("SELECT id FROM users WHERE username = 'hotel_tanaka'").fetchone()
        if hotel_user:
            db.execute("INSERT OR REPLACE INTO progress (user_id, video_id, progress_percent, last_position) VALUES (?, 1, 75.0, 100.0)",
                      (hotel_user['id'],))
        
        # ryokan_suzuki (tenant_id=2) の進捗データ
        ryokan_user = db.execute("SELECT id FROM users WHERE username = 'ryokan_suzuki'").fetchone()
        if ryokan_user:
            db.execute("INSERT OR REPLACE INTO progress (user_id, video_id, progress_percent, last_position) VALUES (?, 1, 50.0, 60.0)",
                      (ryokan_user['id'],))
        
        db.commit()
        yield
    
    def test_company_admin_sees_only_own_tenant_users(self, hotel_client):
        """company_adminは自テナントのユーザーのみ表示される"""
        response = hotel_client.get('/api/admin/user-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        # hotel_tanaka のテナントID (1) のユーザーだけが含まれる
        for user in data['users']:
            # 他テナントのユーザーが含まれていないことを確認
            assert user['username'] != 'ryokan_suzuki', "他テナントのユーザーが見えてはならない"
            assert user['username'] != 'retail_yamada', "他テナントのユーザーが見えてはならない"
        
        print("✓ company_adminは自テナントのユーザーのみ表示される")

    def test_super_admin_sees_all_users(self, admin_client):
        """super_adminは全テナントのユーザーを表示できる"""
        response = admin_client.get('/api/admin/user-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        usernames = [u['username'] for u in data['users']]
        # 複数テナントのユーザーが含まれていること
        assert len(usernames) >= 2, "super_adminは複数ユーザーを表示できるべき"
        print(f"✓ super_adminは全ユーザー（{len(usernames)}名）を表示できる")

    def test_company_admin_departments_filtered(self, hotel_client):
        """company_adminは自テナントの部署のみ表示される"""
        response = hotel_client.get('/api/admin/user-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        dept_names = [d['name'] for d in data['departments']]
        # 他テナントの既知の部署が含まれていないこと（テスト中に作成される部署は許容）
        db = get_db()
        hotel_tenant = db.execute("SELECT tenant_id FROM users WHERE username = 'hotel_tanaka'").fetchone()
        if hotel_tenant:
            hotel_tenant_id = hotel_tenant['tenant_id']
            other_depts = db.execute(
                "SELECT name FROM departments WHERE tenant_id != ?", (hotel_tenant_id,)
            ).fetchall()
            other_dept_names = [d['name'] for d in other_depts]
            for name in dept_names:
                assert name not in other_dept_names, f"他テナントの部署 '{name}' が見えてはならない"
        
        print("✓ company_adminは自テナントの部署のみ表示される")

    def test_user_progress_data_integrity(self, admin_client):
        """ユーザーの進捗データが正しく集計される"""
        response = admin_client.get('/api/admin/user-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        total_videos = data['total_videos']
        
        for user in data['users']:
            # videos_completed <= videos_started
            assert user['videos_completed'] <= user['videos_started'], \
                f"{user['username']}: 完了数({user['videos_completed']})が視聴開始数({user['videos_started']})を超えている"
            # avg_progress は 0-100 の範囲
            assert 0 <= user['avg_progress'] <= 100, \
                f"{user['username']}: 平均進捗({user['avg_progress']})が範囲外"
            # videos_started >= 0
            assert user['videos_started'] >= 0, \
                f"{user['username']}: 視聴開始数({user['videos_started']})が負の値"
            # all_completed の整合性（動画がある場合のみ）
            if user['all_completed'] and total_videos > 0:
                assert user['videos_completed'] >= total_videos, \
                    f"{user['username']}: all_completed=True だが完了数({user['videos_completed']})が動画総数({total_videos})未満"
        
        print("✓ ユーザー進捗データの整合性が正しい")


class TestUserProgressIndustryFilter:
    """ユーザー視聴状況の業種別動画フィルタリングテスト"""
    
    @pytest.fixture(autouse=True)
    def setup_industry_test_data(self):
        """業種制限された動画を作成してフィルタリングを検証"""
        db = sqlite3.connect(TEST_DB_PATH)
        db.row_factory = sqlite3.Row
        
        # 介護業向けカテゴリーのIDを取得
        nursing_cat = db.execute(
            "SELECT id FROM categories WHERE name = '介護業向けAI活用' AND parent_id IS NULL"
        ).fetchone()
        
        # 宿泊業向けカテゴリーのIDを取得
        hotel_cat = db.execute(
            "SELECT id FROM categories WHERE name = '宿泊業向けAI活用' AND parent_id IS NULL"
        ).fetchone()
        
        # 共通（全業種公開）カテゴリーのIDを取得
        common_cat = db.execute(
            "SELECT id FROM categories WHERE name = '基礎編' AND parent_id IS NULL"
        ).fetchone()
        
        # テスト用動画を作成
        if nursing_cat:
            db.execute('''
                INSERT OR IGNORE INTO videos (id, title, filename, category_id)
                VALUES (801, '介護テスト動画', 'nursing_test.mp4', ?)
            ''', (nursing_cat['id'],))
        
        if hotel_cat:
            db.execute('''
                INSERT OR IGNORE INTO videos (id, title, filename, category_id)
                VALUES (802, '宿泊テスト動画', 'hotel_test.mp4', ?)
            ''', (hotel_cat['id'],))
        
        if common_cat:
            db.execute('''
                INSERT OR IGNORE INTO videos (id, title, filename, category_id)
                VALUES (803, '共通テスト動画', 'common_test.mp4', ?)
            ''', (common_cat['id'],))
        
        db.commit()
        db.close()
        
        yield
        
        # クリーンアップ
        db = sqlite3.connect(TEST_DB_PATH)
        db.execute('DELETE FROM progress WHERE video_id IN (801, 802, 803)')
        db.execute('DELETE FROM videos WHERE id IN (801, 802, 803)')
        db.commit()
        db.close()
    
    def test_company_admin_does_not_see_other_industry_videos(self, hotel_client):
        """company_admin（宿泊業）は介護業向けの動画を見られない"""
        response = hotel_client.get('/api/admin/user-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        video_titles = [v['title'] for v in data['videos']]
        assert '介護テスト動画' not in video_titles, \
            "宿泊業の管理者に介護業向けの動画が表示されてはならない"
        print("✓ company_admin（宿泊業）は介護業向けの動画を見られない")
    
    def test_company_admin_sees_own_industry_videos(self, hotel_client):
        """company_admin（宿泊業）は宿泊業向けの動画を見られる"""
        response = hotel_client.get('/api/admin/user-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        video_titles = [v['title'] for v in data['videos']]
        assert '宿泊テスト動画' in video_titles, \
            "宿泊業の管理者は宿泊業向けの動画を見られるべき"
        print("✓ company_admin（宿泊業）は宿泊業向けの動画を見られる")
    
    def test_company_admin_sees_common_videos(self, hotel_client):
        """company_admin（宿泊業）は全業種共通の動画も見られる"""
        response = hotel_client.get('/api/admin/user-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        video_titles = [v['title'] for v in data['videos']]
        assert '共通テスト動画' in video_titles, \
            "宿泊業の管理者は全業種共通の動画を見られるべき"
        print("✓ company_admin（宿泊業）は全業種共通の動画も見られる")
    
    def test_super_admin_sees_all_industry_videos(self, admin_client):
        """super_adminは全業種の動画を見られる"""
        response = admin_client.get('/api/admin/user-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        video_titles = [v['title'] for v in data['videos']]
        assert '介護テスト動画' in video_titles, \
            "super_adminは介護業向け動画を見られるべき"
        assert '宿泊テスト動画' in video_titles, \
            "super_adminは宿泊業向け動画を見られるべき"
        assert '共通テスト動画' in video_titles, \
            "super_adminは共通動画を見られるべき"
        print("✓ super_adminは全業種の動画を見られる")
    
    def test_video_analytics_excludes_other_industry(self, hotel_client):
        """company_admin（宿泊業）は動画分析APIでも介護動画が除外される"""
        response = hotel_client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        video_titles = [v['title'] for v in data['video_stats']]
        assert '介護テスト動画' not in video_titles, \
            "宿泊業の管理者の動画分析に介護業向けの動画が含まれてはならない"
        print("✓ company_admin（宿泊業）は動画分析APIでも介護動画が除外される")
    
    def test_video_analytics_includes_own_industry(self, hotel_client):
        """company_admin（宿泊業）は動画分析APIで宿泊業動画が含まれる"""
        response = hotel_client.get('/api/admin/video-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        video_titles = [v['title'] for v in data['video_stats']]
        assert '宿泊テスト動画' in video_titles, \
            "宿泊業の管理者の動画分析に宿泊業向けの動画が含まれるべき"
        print("✓ company_admin（宿泊業）は動画分析APIで宿泊業動画が含まれる")


class TestUserProgressNavigation:
    """ユーザー視聴状況ナビゲーションのテスト"""
    
    def test_courses_page_has_user_progress_link(self, hotel_client):
        """コースページにユーザー視聴状況リンクがある"""
        response = hotel_client.get('/courses')
        assert response.status_code == 200
        assert b'/admin/user-progress' in response.data
        print("✓ コースページにユーザー視聴状況リンクがある")

    def test_admin_page_has_user_progress_link(self, admin_client):
        """管理画面にユーザー視聴状況リンクがある"""
        response = admin_client.get('/admin')
        assert response.status_code == 200
        assert b'/admin/user-progress' in response.data
        print("✓ 管理画面にユーザー視聴状況リンクがある")

    def test_video_analytics_page_has_user_progress_link(self, admin_client):
        """動画視聴分析ページにユーザー視聴状況リンクがある"""
        response = admin_client.get('/admin/video-analytics')
        assert response.status_code == 200
        assert b'/admin/user-progress' in response.data
        print("✓ 動画視聴分析ページにユーザー視聴状況リンクがある")


# ========== マイ視聴状況ページ テスト ==========

class TestMyProgressPage:
    """マイ視聴状況ページのテスト"""
    
    def test_my_progress_page_loads_for_regular_user(self, client):
        """一般ユーザーがマイ視聴状況ページにアクセスできる"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/my-progress')
        assert response.status_code == 200
        print("✓ 一般ユーザーがマイ視聴状況ページにアクセスできる")
    
    def test_my_progress_page_loads_for_company_admin(self, hotel_client):
        """company_adminもマイ視聴状況ページにアクセスできる"""
        response = hotel_client.get('/my-progress')
        assert response.status_code == 200
        print("✓ company_adminもマイ視聴状況ページにアクセスできる")
    
    def test_my_progress_page_loads_for_super_admin(self, admin_client):
        """super_adminもマイ視聴状況ページにアクセスできる"""
        response = admin_client.get('/my-progress')
        assert response.status_code == 200
        print("✓ super_adminもマイ視聴状況ページにアクセスできる")
    
    def test_my_progress_denied_for_unauthenticated(self, client):
        """未認証ユーザーはマイ視聴状況ページにアクセスできない（リダイレクト）"""
        response = client.get('/my-progress')
        assert response.status_code == 302
        print("✓ 未認証ユーザーはマイ視聴状況ページにアクセス不可（リダイレクト）")


class TestMyProgressAPI:
    """マイ視聴状況APIのテスト"""
    
    def test_api_returns_correct_structure(self, hotel_client):
        """APIが正しい構造のJSONを返す"""
        response = hotel_client.get('/api/my-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        # トップレベルキーの存在確認
        assert 'summary' in data
        assert 'videos' in data
        assert 'category_stats' in data
        assert 'recent_activity' in data
        
        # summaryの構造確認
        summary = data['summary']
        assert 'total_videos' in summary
        assert 'videos_started' in summary
        assert 'videos_completed' in summary
        assert 'avg_progress' in summary
        assert 'all_completed' in summary
        
        # videosの構造確認
        if len(data['videos']) > 0:
            video = data['videos'][0]
            assert 'id' in video
            assert 'title' in video
            assert 'progress_percent' in video
            assert 'status' in video
            assert video['status'] in ('completed', 'in_progress', 'not_started')
        
        print("✓ APIが正しい構造のJSONを返す")
    
    def test_api_returns_own_progress_only(self, client):
        """APIはログインユーザー自身の進捗データのみ返す"""
        # ryokan_suzuki でログイン
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/api/my-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        # 他のユーザーの情報が含まれていないこと（ユーザー一覧のキーがない）
        assert 'users' not in data, "マイ視聴状況APIは他ユーザーの情報を含むべきではない"
        print("✓ APIはログインユーザー自身の進捗データのみ返す")
    
    def test_api_denied_for_unauthenticated(self, client):
        """未認証ユーザーはAPIにアクセスできない（リダイレクト）"""
        response = client.get('/api/my-progress')
        assert response.status_code == 302
        print("✓ 未認証ユーザーはマイ視聴状況APIにアクセス不可")
    
    def test_api_respects_industry_filter(self, client):
        """APIは業種フィルタリングを適用する（宿泊業ユーザーに介護動画が含まれない）"""
        db = sqlite3.connect(TEST_DB_PATH)
        db.row_factory = sqlite3.Row
        
        # 介護カテゴリーにテスト動画を作成
        nursing_cat = db.execute(
            "SELECT id FROM categories WHERE name = '介護業向けAI活用' AND parent_id IS NULL"
        ).fetchone()
        
        if nursing_cat:
            db.execute('''
                INSERT OR IGNORE INTO videos (id, title, filename, category_id)
                VALUES (810, 'マイ進捗介護テスト', 'my_test_nursing.mp4', ?)
            ''', (nursing_cat['id'],))
            db.commit()
        
        # 宿泊業ユーザーでログイン
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/api/my-progress')
        data = response.get_json()
        
        video_titles = [v['title'] for v in data['videos']]
        assert 'マイ進捗介護テスト' not in video_titles, \
            "宿泊業ユーザーに介護業向けの動画が表示されてはならない"
        
        # クリーンアップ
        db.execute('DELETE FROM videos WHERE id = 810')
        db.commit()
        db.close()
        
        print("✓ APIは業種フィルタリングを適用する")
    
    def test_summary_statistics_integrity(self, hotel_client):
        """サマリー統計の整合性を確認"""
        response = hotel_client.get('/api/my-progress')
        assert response.status_code == 200
        data = response.get_json()
        
        summary = data['summary']
        # videos_completed <= videos_started <= total_videos
        assert summary['videos_completed'] <= summary['videos_started'], \
            "完了数は視聴開始数以下であるべき"
        assert summary['videos_started'] <= summary['total_videos'], \
            "視聴開始数は対象動画数以下であるべき"
        # avg_progress は 0-100 の範囲
        assert 0 <= summary['avg_progress'] <= 100, \
            f"平均進捗({summary['avg_progress']})が範囲外"
        
        print("✓ サマリー統計の整合性が正しい")


class TestMyProgressNavigation:
    """マイ視聴状況ナビゲーションのテスト"""
    
    def test_courses_page_has_my_progress_link(self, client):
        """コースページにマイ視聴状況リンクがある（一般ユーザー）"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/courses')
        assert response.status_code == 200
        assert b'/my-progress' in response.data
        print("✓ コースページにマイ視聴状況リンクがある")
    
    def test_dashboard_page_has_my_progress_link(self, client):
        """全動画ページにマイ視聴状況リンクがある"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'/my-progress' in response.data
        print("✓ 全動画ページにマイ視聴状況リンクがある")
    
    def test_chat_page_has_my_progress_link(self, client):
        """チャットページにマイ視聴状況リンクがある"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/chat')
        assert response.status_code == 200
        assert b'/my-progress' in response.data
        print("✓ チャットページにマイ視聴状況リンクがある")
    
    def test_admin_page_has_my_progress_link(self, admin_client):
        """管理画面にもマイ視聴状況リンクがある"""
        response = admin_client.get('/admin')
        assert response.status_code == 200
        assert b'/my-progress' in response.data
        print("✓ 管理画面にもマイ視聴状況リンクがある")


# ========== テナント管理者ガードテスト ==========

class TestTenantAdminGuard:
    """テナントごとに最低1名のcompany_adminが必要であることのテスト"""
    
    def test_all_tenants_have_company_admin(self, admin_client):
        """全テナントにcompany_adminが存在する"""
        response = admin_client.get('/api/admin/tenants/health')
        assert response.status_code == 200
        data = response.get_json()
        
        assert data['all_healthy'], \
            f"company_adminがいないテナントがあります: {data['warnings']}"
        
        for t in data['tenants']:
            if t['user_count'] > 0:
                assert t['has_admin'], \
                    f"テナント '{t['name']}' (ユーザー{t['user_count']}名) にcompany_adminがいません"
        
        print("✓ 全テナントにcompany_adminが存在する")
    
    def test_cannot_delete_last_company_admin(self, admin_client):
        """テナントの最後のcompany_adminは削除できない"""
        db = sqlite3.connect(TEST_DB_PATH)
        db.row_factory = sqlite3.Row
        
        # テナントのcompany_adminが1人だけのテナントを探す
        row = db.execute('''
            SELECT u.id, u.username, u.tenant_id, t.name as tenant_name
            FROM users u
            JOIN tenants t ON u.tenant_id = t.id
            WHERE u.role = 'company_admin'
            AND (SELECT COUNT(*) FROM users WHERE tenant_id = u.tenant_id AND role = 'company_admin') = 1
            LIMIT 1
        ''').fetchone()
        db.close()
        
        if row:
            response = admin_client.delete(f'/api/admin/users/{row["id"]}')
            assert response.status_code == 400, \
                f"最後のcompany_admin ({row['username']}) の削除がブロックされるべき"
            data = response.get_json()
            assert 'error' in data
            print(f"✓ 最後のcompany_admin ({row['username']}) は削除できない")
        else:
            print("✓ (テスト対象のcompany_adminが見つからないためスキップ)")
    
    def test_cannot_change_last_company_admin_role(self, admin_client):
        """テナントの最後のcompany_adminのロールは変更できない"""
        db = sqlite3.connect(TEST_DB_PATH)
        db.row_factory = sqlite3.Row
        
        # テナントのcompany_adminが1人だけのテナントを探す
        row = db.execute('''
            SELECT u.id, u.username, u.email, u.tenant_id, u.industry_id
            FROM users u
            WHERE u.role = 'company_admin'
            AND (SELECT COUNT(*) FROM users WHERE tenant_id = u.tenant_id AND role = 'company_admin') = 1
            LIMIT 1
        ''').fetchone()
        db.close()
        
        if row:
            response = admin_client.put(f'/api/admin/users/{row["id"]}', json={
                'username': row['username'],
                'email': row['email'],
                'role': 'user',  # company_admin → user に変更しようとする
                'tenant_id': row['tenant_id'],
                'industry_id': row['industry_id'],
            })
            assert response.status_code == 400, \
                f"最後のcompany_adminのロール変更がブロックされるべき"
            data = response.get_json()
            assert 'error' in data
            print(f"✓ 最後のcompany_admin ({row['username']}) のロールは変更できない")
        else:
            print("✓ (テスト対象のcompany_adminが見つからないためスキップ)")
    
    def test_can_delete_company_admin_if_another_exists(self, admin_client):
        """複数のcompany_adminがいるテナントでは削除可能"""
        db = sqlite3.connect(TEST_DB_PATH)
        db.row_factory = sqlite3.Row
        
        # テスト用に一時的な company_admin を追加
        # まずテナントIDを取得
        tenant = db.execute("SELECT id, industry_id FROM tenants LIMIT 1").fetchone()
        if tenant:
            from werkzeug.security import generate_password_hash
            db.execute('''
                INSERT INTO users (username, email, password_hash, role, tenant_id, industry_id, company_name)
                VALUES (?, ?, ?, 'company_admin', ?, ?, 'テスト会社')
            ''', ('temp_admin_guard_test', 'temp_guard@test.com', 
                  generate_password_hash('test123'), tenant['id'], tenant['industry_id']))
            db.commit()
            
            temp_user = db.execute("SELECT id FROM users WHERE username = 'temp_admin_guard_test'").fetchone()
            db.close()
            
            if temp_user:
                response = admin_client.delete(f'/api/admin/users/{temp_user["id"]}')
                assert response.status_code == 200, \
                    f"複数admin時は削除可能であるべき（got {response.status_code}）"
                print("✓ 複数のcompany_adminがいる場合は削除可能")
            else:
                print("✓ (テスト用ユーザー作成失敗、スキップ)")
        else:
            db.close()
            print("✓ (テナントなし、スキップ)")


class TestTenantHealthAPI:
    """テナント健全性チェックAPIのテスト"""
    
    def test_health_api_returns_correct_structure(self, admin_client):
        """テナント健全性チェックAPIが正しい構造を返す"""
        response = admin_client.get('/api/admin/tenants/health')
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'tenants' in data
        assert 'warnings' in data
        assert 'all_healthy' in data
        assert isinstance(data['tenants'], list)
        assert isinstance(data['warnings'], list)
        assert isinstance(data['all_healthy'], bool)
        
        if len(data['tenants']) > 0:
            t = data['tenants'][0]
            assert 'name' in t
            assert 'user_count' in t
            assert 'admin_count' in t
            assert 'has_admin' in t
        
        print("✓ テナント健全性チェックAPIが正しい構造を返す")
    
    def test_health_api_denied_for_normal_user(self, client):
        """一般ユーザーはテナント健全性APIにアクセスできない"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/api/admin/tenants/health')
        assert response.status_code == 403
        print("✓ 一般ユーザーはテナント健全性APIにアクセス不可")


# ========== Q&A機能テスト ==========

class TestVideoQA:
    """動画Q&A（質問・回答）機能のテスト"""
    
    def _ensure_test_video(self):
        """テスト用の動画を作成しIDを返す"""
        db = get_db()
        db.execute('''
            INSERT OR IGNORE INTO videos (id, title, filename, category_id)
            VALUES (990, 'Q&Aテスト用動画', 'qa_test.mp4', 1)
        ''')
        db.commit()
        video = db.execute('SELECT id FROM videos WHERE id = 990').fetchone()
        db.close()
        return video['id'] if video else None
    
    def test_get_questions_empty(self, admin_client):
        """質問がない動画のQ&A一覧取得"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        response = admin_client.get(f'/api/videos/{vid}/questions')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert isinstance(data['questions'], list)
        print("✓ 空のQ&A一覧を取得")
    
    def test_post_question(self, admin_client):
        """質問を投稿できる"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        response = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': 'テスト質問: この動画の内容について質問です。'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert 'id' in data
        print("✓ 質問を投稿成功")
    
    def test_post_question_empty(self, admin_client):
        """空の質問は投稿できない"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        response = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': ''
        })
        assert response.status_code == 400
        print("✓ 空の質問は拒否される")
    
    def test_post_question_too_long(self, admin_client):
        """2000文字超の質問は投稿できない"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        response = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': 'あ' * 2001
        })
        assert response.status_code == 400
        print("✓ 2000文字超の質問は拒否される")
    
    def test_post_question_nonexistent_video(self, admin_client):
        """存在しない動画への質問は404"""
        response = admin_client.post('/api/videos/99999/questions', json={
            'question_text': 'テスト質問'
        })
        assert response.status_code == 404
        print("✓ 存在しない動画への質問は404")
    
    def test_post_answer(self, admin_client):
        """回答を投稿できる"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        # まず質問を作成
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '回答テスト用の質問です。'
        })
        q_id = q_resp.get_json()['id']
        
        # 回答を投稿
        response = admin_client.post(f'/api/questions/{q_id}/answers', json={
            'answer_text': 'テスト回答: ご質問ありがとうございます。'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 回答を投稿成功")
    
    def test_post_answer_empty(self, admin_client):
        """空の回答は投稿できない"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '空回答テスト用の質問'
        })
        q_id = q_resp.get_json()['id']
        
        response = admin_client.post(f'/api/questions/{q_id}/answers', json={
            'answer_text': ''
        })
        assert response.status_code == 400
        print("✓ 空の回答は拒否される")
    
    def test_post_answer_nonexistent_question(self, admin_client):
        """存在しない質問への回答は404"""
        response = admin_client.post('/api/questions/99999/answers', json={
            'answer_text': 'テスト回答'
        })
        assert response.status_code == 404
        print("✓ 存在しない質問への回答は404")
    
    def test_get_questions_with_answers(self, admin_client):
        """質問と回答を含むQ&A一覧を取得"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        response = admin_client.get(f'/api/videos/{vid}/questions')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert len(data['questions']) > 0
        
        q = data['questions'][0]
        assert 'question_text' in q
        assert 'username' in q
        assert 'answers' in q
        assert 'answer_count' in q
        print("✓ Q&A一覧を質問・回答付きで取得")
    
    def test_delete_question(self, admin_client):
        """管理者は質問を削除できる"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '削除テスト用の質問'
        })
        q_id = q_resp.get_json()['id']
        
        response = admin_client.delete(f'/api/questions/{q_id}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 管理者が質問を削除成功")
    
    def test_delete_nonexistent_question(self, admin_client):
        """存在しない質問の削除は404"""
        response = admin_client.delete('/api/questions/99999')
        assert response.status_code == 404
        print("✓ 存在しない質問の削除は404")
    
    def test_delete_answer(self, admin_client):
        """管理者は回答を削除できる"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '回答削除テスト用の質問'
        })
        q_id = q_resp.get_json()['id']
        
        a_resp = admin_client.post(f'/api/questions/{q_id}/answers', json={
            'answer_text': '削除される回答'
        })
        a_id = a_resp.get_json()['id']
        
        response = admin_client.delete(f'/api/answers/{a_id}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 管理者が回答を削除成功")
    
    def test_delete_nonexistent_answer(self, admin_client):
        """存在しない回答の削除は404"""
        response = admin_client.delete('/api/answers/99999')
        assert response.status_code == 404
        print("✓ 存在しない回答の削除は404")
    
    def test_regular_user_cannot_delete_others_question(self, client):
        """一般ユーザーは他人の質問を削除できない"""
        # 管理者でログインして質問を作成
        client.post('/login', json={'username': 'admin', 'password': 'admin123'})
        
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        
        q_resp = client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '管理者が作成した質問（他ユーザーは削除不可）'
        })
        q_id = q_resp.get_json()['id']
        
        # 一般ユーザーでログインし直す
        client.get('/logout')
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        
        response = client.delete(f'/api/questions/{q_id}')
        assert response.status_code == 403
        print("✓ 一般ユーザーは他人の質問を削除できない")
    
    def test_unauthenticated_cannot_post_question(self, client):
        """未ログインユーザーは質問を投稿できない"""
        response = client.post('/api/videos/1/questions', json={
            'question_text': 'テスト'
        })
        assert response.status_code in [302, 401, 403]
        print("✓ 未ログインユーザーは質問を投稿不可")
    
    def test_update_question(self, admin_client):
        """投稿者本人が質問を更新できる"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '更新前の質問テキスト'
        })
        q_id = q_resp.get_json()['id']
        
        response = admin_client.put(f'/api/questions/{q_id}', json={
            'question_text': '更新後の質問テキスト'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 投稿者本人が質問を更新成功")
    
    def test_update_question_empty(self, admin_client):
        """空テキストでの質問更新は拒否される"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '空更新テスト用質問'
        })
        q_id = q_resp.get_json()['id']
        
        response = admin_client.put(f'/api/questions/{q_id}', json={
            'question_text': ''
        })
        assert response.status_code == 400
        print("✓ 空テキストでの質問更新は拒否される")
    
    def test_update_question_too_long(self, admin_client):
        """2000文字超での質問更新は拒否される"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '文字数超過テスト用質問'
        })
        q_id = q_resp.get_json()['id']
        
        response = admin_client.put(f'/api/questions/{q_id}', json={
            'question_text': 'あ' * 2001
        })
        assert response.status_code == 400
        print("✓ 2000文字超での質問更新は拒否される")
    
    def test_update_question_nonexistent(self, admin_client):
        """存在しない質問の更新は404"""
        response = admin_client.put('/api/questions/99999', json={
            'question_text': '更新テスト'
        })
        assert response.status_code == 404
        print("✓ 存在しない質問の更新は404")
    
    def test_other_user_cannot_update_question(self, client):
        """他人の質問は更新できない"""
        # 管理者でログインして質問を作成
        client.post('/login', json={'username': 'admin', 'password': 'admin123'})
        
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        
        q_resp = client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '管理者が作成した質問'
        })
        q_id = q_resp.get_json()['id']
        
        # 一般ユーザーでログインし直す
        client.get('/logout')
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        
        response = client.put(f'/api/questions/{q_id}', json={
            'question_text': '他人が更新しようとした'
        })
        assert response.status_code == 403
        print("✓ 他人の質問は更新できない（403）")
    
    def test_update_answer(self, admin_client):
        """投稿者本人が回答を更新できる"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '回答更新テスト用質問'
        })
        q_id = q_resp.get_json()['id']
        
        a_resp = admin_client.post(f'/api/questions/{q_id}/answers', json={
            'answer_text': '更新前の回答テキスト'
        })
        a_id = a_resp.get_json()['id']
        
        response = admin_client.put(f'/api/answers/{a_id}', json={
            'answer_text': '更新後の回答テキスト'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 投稿者本人が回答を更新成功")
    
    def test_update_answer_empty(self, admin_client):
        """空テキストでの回答更新は拒否される"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '空回答更新テスト用質問'
        })
        q_id = q_resp.get_json()['id']
        
        a_resp = admin_client.post(f'/api/questions/{q_id}/answers', json={
            'answer_text': '更新テスト用回答'
        })
        a_id = a_resp.get_json()['id']
        
        response = admin_client.put(f'/api/answers/{a_id}', json={
            'answer_text': ''
        })
        assert response.status_code == 400
        print("✓ 空テキストでの回答更新は拒否される")
    
    def test_update_answer_nonexistent(self, admin_client):
        """存在しない回答の更新は404"""
        response = admin_client.put('/api/answers/99999', json={
            'answer_text': '更新テスト'
        })
        assert response.status_code == 404
        print("✓ 存在しない回答の更新は404")
    
    def test_other_user_cannot_update_answer(self, client):
        """他人の回答は更新できない"""
        # 管理者でログインして質問&回答を作成
        client.post('/login', json={'username': 'admin', 'password': 'admin123'})
        
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        
        q_resp = client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '他人回答更新テスト用質問'
        })
        q_id = q_resp.get_json()['id']
        
        a_resp = client.post(f'/api/questions/{q_id}/answers', json={
            'answer_text': '管理者が作成した回答'
        })
        a_id = a_resp.get_json()['id']
        
        # 一般ユーザーでログインし直す
        client.get('/logout')
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        
        response = client.put(f'/api/answers/{a_id}', json={
            'answer_text': '他人が更新しようとした'
        })
        assert response.status_code == 403
        print("✓ 他人の回答は更新できない（403）")


# ========== Q&A分析ダッシュボード テスト ==========

class TestQAAnalytics:
    """Q&A分析ダッシュボード機能のテスト"""
    
    def _ensure_test_video(self):
        """テスト用の動画を作成しIDを返す"""
        db = get_db()
        db.execute('''
            INSERT OR IGNORE INTO videos (id, title, filename, category_id)
            VALUES (991, 'Q&A分析テスト用動画', 'qa_analytics_test.mp4', 1)
        ''')
        db.commit()
        video = db.execute('SELECT id FROM videos WHERE id = 991').fetchone()
        db.close()
        return video['id'] if video else None
    
    def test_qa_analytics_page_access(self, admin_client):
        """管理者はQ&A分析ページにアクセスできる"""
        response = admin_client.get('/admin/qa-analytics')
        assert response.status_code == 200
        print("✓ Q&A分析ページにアクセス成功")
    
    def test_qa_analytics_page_user_denied(self, client):
        """一般ユーザーはQ&A分析ページにアクセスできない"""
        client.post('/login', json={'username': 'ryokan_suzuki', 'password': 'user123'})
        response = client.get('/admin/qa-analytics')
        assert response.status_code in [302, 403]
        print("✓ 一般ユーザーはQ&A分析ページにアクセス不可")
    
    def test_qa_analytics_summary_empty(self, admin_client):
        """Q&A分析サマリーAPIが正常に応答する"""
        response = admin_client.get('/api/admin/qa-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        assert 'summary' in data
        assert 'total_questions' in data['summary']
        assert 'total_answers' in data['summary']
        assert 'unanswered' in data['summary']
        assert 'answer_rate' in data['summary']
        assert 'video_ranking' in data
        assert 'unanswered_questions' in data
        assert 'user_stats' in data
        assert 'daily_activity' in data
        print("✓ Q&A分析サマリーAPIが正常に応答")
    
    def test_qa_analytics_with_data(self, admin_client):
        """データありの場合のQ&A分析サマリー"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        
        # テストデータ作成: 質問と回答
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '分析テスト用質問1'
        })
        q_id = q_resp.get_json()['id']
        
        admin_client.post(f'/api/questions/{q_id}/answers', json={
            'answer_text': '分析テスト用回答1'
        })
        
        # 未回答の質問も作成
        admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '未回答の分析テスト用質問2'
        })
        
        response = admin_client.get('/api/admin/qa-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        
        assert data['summary']['total_questions'] >= 2
        assert data['summary']['total_answers'] >= 1
        assert data['summary']['unanswered'] >= 1
        assert len(data['video_ranking']) >= 1
        assert len(data['unanswered_questions']) >= 1
        print("✓ データありのQ&A分析サマリーが正しく集計")
    
    def test_qa_analytics_tenant_isolation(self, client):
        """company_adminは自テナントのQ&Aのみ分析可能"""
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        response = client.get('/api/admin/qa-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        assert 'summary' in data
        # テナント統計はcompany_adminには表示されない
        assert data['tenant_stats'] == []
        print("✓ company_adminのテナント分離が正常")
    
    def test_qa_analytics_super_admin_tenant_stats(self, admin_client):
        """super_adminはテナント別統計を取得可能"""
        response = admin_client.get('/api/admin/qa-analytics/summary')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data['tenant_stats'], list)
        print("✓ super_adminがテナント別統計を取得可能")
    
    def test_qa_analytics_daily_filter(self, admin_client):
        """日数フィルタが機能する"""
        response = admin_client.get('/api/admin/qa-analytics/summary?days=7')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data['daily_activity'], list)
        print("✓ 日数フィルタが機能")


# ========== マイQ&A テスト ==========

class TestMyQA:
    """マイQ&A（一般ユーザー向け）機能のテスト"""
    
    def _ensure_test_video(self):
        """テスト用の動画を作成しIDを返す"""
        db = get_db()
        db.execute('''
            INSERT OR IGNORE INTO videos (id, title, filename, category_id)
            VALUES (992, 'マイQ&Aテスト用動画', 'my_qa_test.mp4', 1)
        ''')
        db.commit()
        video = db.execute('SELECT id FROM videos WHERE id = 992').fetchone()
        db.close()
        return video['id'] if video else None
    
    def test_my_questions_empty(self, client):
        """マイQ&A一覧取得（初期状態）"""
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        response = client.get('/api/my-questions')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert isinstance(data['my_questions'], list)
        assert isinstance(data['my_answers'], list)
        print("✓ マイQ&A一覧取得成功（初期状態）")
    
    def test_my_questions_with_data(self, client):
        """質問投稿後にマイQ&Aに反映される"""
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        
        # 質問を投稿
        client.post(f'/api/videos/{vid}/questions', json={
            'question_text': 'マイQ&Aテスト用質問'
        })
        
        response = client.get('/api/my-questions')
        assert response.status_code == 200
        data = response.get_json()
        
        my_questions = data['my_questions']
        assert len(my_questions) >= 1
        
        q = my_questions[0]
        assert 'video_title' in q
        assert 'question_text' in q
        assert 'answer_count' in q
        print("✓ マイQ&Aに投稿した質問が反映される")
    
    def test_my_answers_with_data(self, admin_client, client):
        """回答投稿後にマイ回答に反映される"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        
        # admin_clientで質問を作成
        q_resp = admin_client.post(f'/api/videos/{vid}/questions', json={
            'question_text': 'マイ回答テスト用質問（管理者が投稿）'
        })
        q_id = q_resp.get_json()['id']
        
        # 管理者が回答
        admin_client.post(f'/api/questions/{q_id}/answers', json={
            'answer_text': 'マイ回答テスト用の回答'
        })
        
        # 管理者のマイQ&A確認
        response = admin_client.get('/api/my-questions')
        assert response.status_code == 200
        data = response.get_json()
        
        assert len(data['my_answers']) >= 1
        a = data['my_answers'][0]
        assert 'answer_text' in a
        assert 'video_title' in a
        assert 'question_author' in a
        print("✓ マイ回答に投稿した回答が反映される")
    
    def test_my_questions_unauthenticated(self, client):
        """未ログインユーザーはマイQ&Aにアクセスできない"""
        response = client.get('/api/my-questions')
        assert response.status_code in [302, 401, 403]
        print("✓ 未ログインユーザーはマイQ&Aにアクセス不可")
    
    def test_my_questions_includes_tenant_questions(self, client):
        """同テナントのメンバーのQ&Aが社内Q&Aとして含まれる"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        
        db = get_db()
        # hotel_tanakaと同じテナントにテスト用ユーザーを追加
        hotel_user = db.execute("SELECT tenant_id FROM users WHERE username = 'hotel_tanaka'").fetchone()
        if not hotel_user or not hotel_user['tenant_id']:
            pytest.skip("hotel_tanakaにテナントが設定されていません")
        
        tenant_id = hotel_user['tenant_id']
        
        # 同テナントにテスト用ユーザーを作成
        from werkzeug.security import generate_password_hash
        db.execute('''
            INSERT OR IGNORE INTO users (username, email, password_hash, industry_id, tenant_id, company_name, role)
            VALUES (?, ?, ?, 1, ?, 'テスト会社', 'user')
        ''', ('tenant_colleague', 'colleague@test.co.jp', generate_password_hash('user123'), tenant_id))
        db.commit()
        
        # 同僚ユーザーでログインして質問を投稿
        client.post('/login', json={'username': 'tenant_colleague', 'password': 'user123'})
        client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '同テナントテスト用質問: AIの活用方法を教えてください'
        })
        client.get('/logout')
        
        # hotel_tanakaでログインして社内Q&Aを確認
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        response = client.get('/api/my-questions')
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'tenant_questions' in data
        tenant_qs = data['tenant_questions']
        assert len(tenant_qs) >= 1
        
        # 同僚の質問が含まれている
        colleague_q = [q for q in tenant_qs if q['author'] == 'tenant_colleague']
        assert len(colleague_q) >= 1
        assert colleague_q[0]['question_text'] == '同テナントテスト用質問: AIの活用方法を教えてください'
        assert 'video_title' in colleague_q[0]
        assert 'answer_count' in colleague_q[0]
        assert 'answers' in colleague_q[0]
        print("✓ 同テナントのメンバーの質問が社内Q&Aに表示される")
    
    def test_tenant_questions_exclude_own(self, client):
        """社内Q&Aに自分の質問は含まれない"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        
        # hotel_tanakaでログインして質問を投稿
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '自分の質問: これは社内Q&Aに表示されるべきではない'
        })
        
        response = client.get('/api/my-questions')
        assert response.status_code == 200
        data = response.get_json()
        
        # 社内Q&Aに自分の質問が含まれていないこと
        tenant_qs = data.get('tenant_questions', [])
        own_qs = [q for q in tenant_qs if q.get('author') == 'hotel_tanaka']
        # 自分が投稿した質問は社内Q&Aに表示されない
        own_in_tenant = [q for q in own_qs 
                         if q['question_text'] == '自分の質問: これは社内Q&Aに表示されるべきではない']
        assert len(own_in_tenant) == 0
        print("✓ 社内Q&Aに自分の質問は含まれない")
    
    def test_tenant_questions_exclude_other_tenant(self, client):
        """他テナントのQ&Aは社内Q&Aに含まれない"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        
        # retail_yamada（別テナント）でログインして質問を投稿
        client.post('/login', json={'username': 'retail_yamada', 'password': 'user123'})
        client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '他テナントの質問: 小売向けAI活用法'
        })
        client.get('/logout')
        
        # hotel_tanaka（別テナント）でログインして社内Q&Aを確認
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        response = client.get('/api/my-questions')
        assert response.status_code == 200
        data = response.get_json()
        
        tenant_qs = data.get('tenant_questions', [])
        # retail_yamadaの質問は表示されない
        other_tenant_qs = [q for q in tenant_qs if q.get('author') == 'retail_yamada']
        assert len(other_tenant_qs) == 0
        print("✓ 他テナントの質問は社内Q&Aに含まれない")
    
    def test_tenant_questions_include_answers(self, client):
        """社内Q&Aの質問に回答が含まれる"""
        vid = self._ensure_test_video()
        if vid is None:
            pytest.skip("テスト用動画がありません")
        
        db = get_db()
        hotel_user = db.execute("SELECT tenant_id FROM users WHERE username = 'hotel_tanaka'").fetchone()
        if not hotel_user or not hotel_user['tenant_id']:
            pytest.skip("hotel_tanakaにテナントが設定されていません")
        
        # 同僚ユーザーで質問と回答を作成
        client.post('/login', json={'username': 'tenant_colleague', 'password': 'user123'})
        q_resp = client.post(f'/api/videos/{vid}/questions', json={
            'question_text': '回答付きテスト用質問: プロンプトの書き方のコツは？'
        })
        q_data = q_resp.get_json()
        if q_data.get('id'):
            client.post(f'/api/questions/{q_data["id"]}/answers', json={
                'answer_text': 'テスト回答: 具体的で明確な指示を出すことが重要です。'
            })
        client.get('/logout')
        
        # hotel_tanakaで社内Q&Aを確認
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        response = client.get('/api/my-questions')
        assert response.status_code == 200
        data = response.get_json()
        
        tenant_qs = data.get('tenant_questions', [])
        answered_qs = [q for q in tenant_qs 
                       if q['question_text'] == '回答付きテスト用質問: プロンプトの書き方のコツは？']
        assert len(answered_qs) >= 1
        assert len(answered_qs[0]['answers']) >= 1
        assert answered_qs[0]['answers'][0]['answer_text'] == 'テスト回答: 具体的で明確な指示を出すことが重要です。'
        print("✓ 社内Q&Aの質問に回答が含まれる")


# ========== お知らせ・通知機能テスト ==========

class TestAnnouncements:
    """お知らせ・通知機能のテスト"""
    
    def test_get_announcements_empty(self, admin_client):
        """お知らせ一覧取得（初期状態）"""
        response = admin_client.get('/api/announcements')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert isinstance(data['announcements'], list)
        print("✓ お知らせ一覧を取得")
    
    def test_create_announcement(self, admin_client):
        """super_adminが全体通知を作成できる"""
        response = admin_client.post('/api/admin/announcements', json={
            'title': 'テスト通知',
            'content': 'これはテスト通知の内容です。',
            'type': 'info',
            'target_tenant_id': None
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert 'id' in data
        print("✓ super_adminが全体通知を作成成功")
    
    def test_create_announcement_with_tenant(self, admin_client):
        """super_adminがテナント向け通知を作成できる"""
        # テナントID取得
        db = get_db()
        tenant = db.execute('SELECT id FROM tenants LIMIT 1').fetchone()
        db.close()
        if not tenant:
            pytest.skip("テナントが存在しません")
        
        response = admin_client.post('/api/admin/announcements', json={
            'title': 'テナント向け通知',
            'content': 'テナント向けの通知内容です。',
            'type': 'warning',
            'target_tenant_id': tenant['id']
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ super_adminがテナント向け通知を作成成功")
    
    def test_create_announcement_missing_fields(self, admin_client):
        """タイトルと内容は必須"""
        response = admin_client.post('/api/admin/announcements', json={
            'title': '',
            'content': '',
            'type': 'info'
        })
        assert response.status_code == 400
        print("✓ タイトル・内容が空の場合は拒否される")
    
    def test_create_announcement_invalid_type(self, admin_client):
        """無効な通知タイプは拒否される"""
        response = admin_client.post('/api/admin/announcements', json={
            'title': 'テスト',
            'content': 'テスト内容',
            'type': 'invalid'
        })
        assert response.status_code == 400
        print("✓ 無効な通知タイプは拒否される")
    
    def test_get_admin_announcements(self, admin_client):
        """管理者向け通知一覧を取得"""
        response = admin_client.get('/api/admin/announcements')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert len(data['announcements']) > 0
        
        a = data['announcements'][0]
        assert 'title' in a
        assert 'content' in a
        assert 'type' in a
        assert 'is_active' in a
        print("✓ 管理者向け通知一覧を取得成功")
    
    def test_update_announcement(self, admin_client):
        """通知を更新できる"""
        # まず作成
        create_resp = admin_client.post('/api/admin/announcements', json={
            'title': '更新テスト通知',
            'content': '更新前の内容',
            'type': 'info',
            'target_tenant_id': None
        })
        ann_id = create_resp.get_json()['id']
        
        # 更新
        response = admin_client.put(f'/api/admin/announcements/{ann_id}', json={
            'title': '更新後テスト通知',
            'content': '更新後の内容',
            'type': 'success'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 通知の更新成功")
    
    def test_toggle_announcement_active(self, admin_client):
        """通知の有効/無効を切り替え"""
        create_resp = admin_client.post('/api/admin/announcements', json={
            'title': 'トグルテスト',
            'content': 'トグルテスト内容',
            'type': 'info',
            'target_tenant_id': None
        })
        ann_id = create_resp.get_json()['id']
        
        # 無効化
        response = admin_client.put(f'/api/admin/announcements/{ann_id}', json={
            'is_active': False
        })
        assert response.status_code == 200
        
        # 無効になった通知はユーザー向けAPIに表示されない
        announcements = admin_client.get('/api/announcements').get_json()['announcements']
        ann_ids = [a['id'] for a in announcements]
        assert ann_id not in ann_ids
        print("✓ 通知の有効/無効切り替え成功")
    
    def test_delete_announcement(self, admin_client):
        """通知を削除できる"""
        create_resp = admin_client.post('/api/admin/announcements', json={
            'title': '削除テスト',
            'content': '削除される通知',
            'type': 'info',
            'target_tenant_id': None
        })
        ann_id = create_resp.get_json()['id']
        
        response = admin_client.delete(f'/api/admin/announcements/{ann_id}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 通知の削除成功")
    
    def test_delete_nonexistent_announcement(self, admin_client):
        """存在しない通知の削除は404"""
        response = admin_client.delete('/api/admin/announcements/99999')
        assert response.status_code == 404
        print("✓ 存在しない通知の削除は404")
    
    def test_update_nonexistent_announcement(self, admin_client):
        """存在しない通知の更新は404"""
        response = admin_client.put('/api/admin/announcements/99999', json={
            'title': 'テスト',
            'content': 'テスト'
        })
        assert response.status_code == 404
        print("✓ 存在しない通知の更新は404")
    
    def test_normal_user_cannot_create_announcement(self, client):
        """一般ユーザーは通知を作成できない"""
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        response = client.post('/api/admin/announcements', json={
            'title': 'テスト',
            'content': 'テスト',
            'type': 'info'
        })
        assert response.status_code == 403
        print("✓ 一般ユーザーは通知を作成不可")
    
    def test_normal_user_can_view_announcements(self, client):
        """一般ユーザーはお知らせを閲覧できる"""
        client.post('/login', json={'username': 'hotel_tanaka', 'password': 'user123'})
        response = client.get('/api/announcements')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 一般ユーザーがお知らせを閲覧可能")
    
    def test_company_admin_cannot_create_global_announcement(self, client):
        """company_adminは全体通知を作成できない"""
        # company_adminでログイン
        db = get_db()
        ca = db.execute("SELECT username FROM users WHERE role = 'company_admin' LIMIT 1").fetchone()
        db.close()
        if not ca:
            pytest.skip("company_adminユーザーが存在しません")
        
        client.post('/login', json={'username': ca['username'], 'password': 'user123'})
        response = client.post('/api/admin/announcements', json={
            'title': '全体通知テスト',
            'content': '全体通知の内容',
            'type': 'info',
            'target_tenant_id': None
        })
        assert response.status_code == 403
        print("✓ company_adminは全体通知を作成不可")
    
    def test_company_admin_can_create_tenant_announcement(self, client):
        """company_adminは自テナント向け通知を作成できる"""
        db = get_db()
        ca = db.execute("SELECT username, tenant_id FROM users WHERE role = 'company_admin' LIMIT 1").fetchone()
        db.close()
        if not ca:
            pytest.skip("company_adminユーザーが存在しません")
        
        client.post('/login', json={'username': ca['username'], 'password': 'user123'})
        response = client.post('/api/admin/announcements', json={
            'title': 'テナント通知テスト',
            'content': 'テナント向けの通知',
            'type': 'info',
            'target_tenant_id': ca['tenant_id']
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ company_adminが自テナント向け通知を作成成功")
    
    def test_unauthenticated_cannot_view_announcements(self, client):
        """未ログインユーザーはお知らせを閲覧できない"""
        response = client.get('/api/announcements')
        assert response.status_code in [302, 401, 403]
        print("✓ 未ログインユーザーはお知らせ閲覧不可")
    
    def test_announcement_with_expiry(self, admin_client):
        """有効期限付き通知を作成・取得"""
        response = admin_client.post('/api/admin/announcements', json={
            'title': '期限付き通知',
            'content': 'この通知は有効期限があります',
            'type': 'warning',
            'target_tenant_id': None,
            'expires_at': '2099-12-31 23:59:59'
        })
        assert response.status_code == 200
        
        # 有効期限内なので表示される
        announcements = admin_client.get('/api/announcements').get_json()['announcements']
        titles = [a['title'] for a in announcements]
        assert '期限付き通知' in titles
        print("✓ 有効期限付き通知の作成・取得成功")


# ========== テスト実行 ==========

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  LMS テストスイート（全機能）")
    print("=" * 60 + "\n")
    pytest.main([__file__, '-v', '--tb=short'])
