"""
tests/test_like.py —— 点赞接口的自动化测试

"""

from app.models import Answer


def test_like_without_token_returns_401(client):
    """没带 token 点赞 → 401。"""
    resp = client.post("/api/v1/like/1")
    assert resp.status_code == 401


def test_like_answer_and_duplicate(client, auth):
    """点赞成功 → 200；重复点赞 → 400（防重复逻辑）。"""
    token = auth(username="liker")
    client.post(
        "/api/v1/questions",
        json={"title": "题", "content": "内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/api/v1/questions?sort=new").json()[0]["id"]
    aid = client.post(
        f"/api/v1/questions/{qid}/answers",
        json={"content": "答"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]

    first = client.post(f"/api/v1/like/{aid}", headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 200

    second = client.post(f"/api/v1/like/{aid}", headers={"Authorization": f"Bearer {token}"})
    assert second.status_code == 400


def test_unlike_without_token_returns_401(client):
    """没带 token 取消点赞 → 401。"""
    resp = client.delete("/api/v1/like/1")
    assert resp.status_code == 401


def test_unlike_decrements_like_count(client, auth, db_session):
    """点赞后取消 → 200，like_count 回到原来的值。"""
    token = auth(username="unliker")
    client.post(
        "/api/v1/questions",
        json={"title": "题", "content": "内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/api/v1/questions?sort=new").json()[0]["id"]
    aid = client.post(
        f"/api/v1/questions/{qid}/answers",
        json={"content": "答"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]

    client.post(f"/api/v1/like/{aid}", headers={"Authorization": f"Bearer {token}"})
    db_session.commit()
    assert db_session.get(Answer, aid).like_count == 1

    resp = client.delete(f"/api/v1/like/{aid}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["点赞数量"] == 0
    db_session.commit()
    assert db_session.get(Answer, aid).like_count == 0


def test_unlike_not_liked_returns_404(client, auth):
    """没赞过就取消 → 404。"""
    token = auth(username="never_liked")
    client.post(
        "/api/v1/questions",
        json={"title": "题", "content": "内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/api/v1/questions?sort=new").json()[0]["id"]
    aid = client.post(
        f"/api/v1/questions/{qid}/answers",
        json={"content": "答"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]

    resp = client.delete(f"/api/v1/like/{aid}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
