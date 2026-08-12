"""
tests/test_questions.py —— 问题接口的自动化测试
每个 def test_xxx() 就是一个「检查项目」：
- TestClient 模拟浏览器发请求
- assert 是体检标准，不满足就报警（测试失败）
"""


def test_post_question_without_token_returns_401(client):
    """没带 token 发帖 → 应该被 get_current_user 挡下来，返回 401。"""
    resp = client.post("/questions", json={"title": "你好", "content": "内容"})
    assert resp.status_code == 401


def test_register_login_and_post(client, auth):
    """完整链路：注册 → 登录拿 token → 带 token 发帖 → 成功。"""
    token = auth()
    resp = client.post(
        "/questions",
        json={"title": "第一个问题", "content": "问题的详细内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_duplicate_register_returns_400(client):
    """同一个用户名注册两次 → 第二次应该返回 400（用户已存在）。"""
    client.post("/auth/register", json={"username": "bob", "password": "secret123"})
    resp = client.post("/auth/register", json={"username": "bob", "password": "secret123"})
    assert resp.status_code == 400


def test_list_questions_respects_page_size(client, auth):
    """发 3 个问题，请求 size=2 → 应该只返回 2 条。
    """
    for i in range(3):
        token = auth(username=f"user{i}")
        client.post(
            "/questions",
            json={"title": f"问题{i}", "content": "内容"},
            headers={"Authorization": f"Bearer {token}"},
        )
    resp = client.get("/questions?size=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
