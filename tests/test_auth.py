"""
tests/test_auth.py —— 双 token 认证（refresh 接口）的自动化测试
refresh 是双 token 的安全闭环点：access 只能调接口，refresh 只能换新 access，
靠 payload 里的 type 字段区分。这里的测试专门验证「换卡柜台」的规矩：
能换的、不能换的（type 混用）、假卡的。
"""


def _login(client, username="alice", password="secret123"):
    """注册 + 登录，返回完整响应体（含 access_token 和 refresh_token）。"""
    client.post("/api/v1/auth/register", json={"username": username, "password": password})
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return resp.json()


def test_login_returns_two_tokens(client):
    """登录应该同时返回 access_token 和 refresh_token。"""
    data = _login(client)
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"


def test_refresh_returns_new_access_token(client):
    """正常换卡：refresh → 新 access → 新 access 能调受保护接口。"""
    data = _login(client)
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]

    # 新 access 能发帖（受保护接口放行），证明闭环打通
    resp2 = client.post(
        "/api/v1/questions",
        json={"title": "刷新后发帖", "content": "内容"},
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert resp2.status_code == 200


def test_access_token_cannot_be_used_to_refresh(client):
    """最关键的测试：access 冒充 refresh → 401。type 字段的防线在起作用。"""
    data = _login(client)
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": data["access_token"]})
    assert resp.status_code == 401


def test_refresh_with_garbage_token_returns_401(client):
    """乱码 refresh → 验签失败 → 401。"""
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "not.a.jwt"})
    assert resp.status_code == 401
