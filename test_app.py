# -*- coding: utf-8 -*-
"""
LMS アプリケーション テストスイート
========================================
業種別アクセス制御を含む全機能のテスト
"""

import pytest
import sqlite3
import os
import sys

# Windows環境での日本語出力対応
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from app import app, get_db

# ========== テスト設定 ==========

@pytest.fixture
def client():
    """テスト用のFlaskクライアントを作成"""
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
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
    
    def test_normal_user_cannot_access_admin(self, hotel_client):
        """一般ユーザーは管理画面にアクセス不可"""
        response = hotel_client.get('/admin')
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
        assert len(data) == 6  # 6業種
        industry_names = [i['name'] for i in data]
        assert '宿泊' in industry_names
        assert '小売' in industry_names
        assert '飲食' in industry_names
        assert '介護' in industry_names
        assert '医療' in industry_names
        assert '教育' in industry_names
        print("✓ 業種一覧を正常に取得")
    
    def test_create_industry(self, admin_client):
        """新しい業種を作成"""
        response = admin_client.post('/api/admin/industries', json={
            'name': 'テスト業種',
            'name_en': 'Test Industry',
            'description': 'テスト用の業種です',
            'icon': 'bi-gear',
            'color': '#ff0000'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        print("✓ 新しい業種を作成成功")
    
    def test_normal_user_cannot_create_industry(self, hotel_client):
        """一般ユーザーは業種を作成不可"""
        response = hotel_client.post('/api/admin/industries', json={
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
        response = admin_client.post('/api/admin/users', json={
            'username': 'test_new_user',
            'email': 'test_new@example.com',
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
    
    def test_normal_user_cannot_create_user(self, hotel_client):
        """一般ユーザーはユーザー作成不可"""
        response = hotel_client.post('/api/admin/users', json={
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


# ========== テスト実行 ==========

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  LMS テストスイート")
    print("=" * 60 + "\n")
    pytest.main([__file__, '-v', '--tb=short'])
