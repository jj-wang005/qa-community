"""
tests/test_questions.py —— 问题接口的自动化测试
每个 def test_xxx() 就是一个「检查项目」：
- TestClient 模拟浏览器发请求
- assert 是体检标准，不满足就报警（测试失败）
"""

from app.models import Answer, Like, Question


def test_post_question_without_token_returns_401(client):
    """没带 token 发帖 → 应该被 get_current_user 挡下来，返回 401。"""
    resp = client.post("/api/v1/questions", json={"title": "你好", "content": "内容"})
    assert resp.status_code == 401


def test_register_login_and_post(client, auth):
    """完整链路：注册 → 登录拿 token → 带 token 发帖 → 成功。"""
    token = auth()
    resp = client.post(
        "/api/v1/questions",
        json={"title": "第一个问题", "content": "问题的详细内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_duplicate_register_returns_400(client):
    """同一个用户名注册两次 → 第二次应该返回 400（用户已存在）。"""
    client.post("/api/v1/auth/register", json={"username": "bob", "password": "secret123"})
    resp = client.post("/api/v1/auth/register", json={"username": "bob", "password": "secret123"})
    assert resp.status_code == 400


def test_list_questions_respects_page_size(client, auth):
    """发 3 个问题，请求 size=2 → 应该只返回 2 条。
    """
    for i in range(3):
        token = auth(username=f"user{i}")
        client.post(
            "/api/v1/questions",
            json={"title": f"问题{i}", "content": "内容"},
            headers={"Authorization": f"Bearer {token}"},
        )
    resp = client.get("/api/v1/questions?size=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_delete_question_without_token_returns_401(client):
    resp = client.delete("/api/v1/questions/1")
    assert resp.status_code == 401


def test_question_author_can_delete_question_and_cascade_answers(client, auth, db_session):
    token = auth(username="question_owner")
    client.post(
        "/api/v1/questions",
        json={"title": "待删除问题", "content": "内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/api/v1/questions?sort=new").json()[0]["id"]
    aid = client.post(
        f"/api/v1/questions/{qid}/answers",
        json={"content": "待删除回答"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]
    client.post(f"/api/v1/like/{aid}", headers={"Authorization": f"Bearer {token}"})
    client.get(f"/api/v1/questions/{qid}")
    client.get("/api/v1/questions?sort=new")

    resp = client.delete(
        f"/api/v1/questions/{qid}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert client.get(f"/api/v1/questions/{qid}").status_code == 404
    assert db_session.get(Question, qid) is None
    assert db_session.get(Answer, aid) is None
    assert db_session.query(Like).filter_by(answer_id=aid).first() is None
    assert client.get("/api/v1/questions?sort=new").json() == []


def test_non_author_cannot_delete_question(client, auth):
    owner_token = auth(username="owner")
    client.post(
        "/api/v1/questions",
        json={"title": "别人的问题", "content": "内容"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    qid = client.get("/api/v1/questions?sort=new").json()[0]["id"]
    other_token = auth(username="other")

    resp = client.delete(
        f"/api/v1/questions/{qid}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert resp.status_code == 403


def test_delete_missing_question_returns_404(client, auth):
    token = auth(username="missing_question")
    resp = client.delete(
        "/api/v1/questions/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
