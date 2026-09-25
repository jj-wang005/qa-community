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


def test_answer_list_returns_current_users_like_state(client, auth):
    """公共回答列表可共享缓存，但 is_liked 必须按当前用户单独计算。"""
    token = auth(username="like_state")
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/v1/questions",
        json={"title": "点赞状态", "content": "测试回答列表"},
        headers=headers,
    )
    qid = client.get("/api/v1/questions?sort=new").json()[0]["id"]
    answer_id = client.post(
        f"/api/v1/questions/{qid}/answers",
        json={"content": "可点赞的回答"},
        headers=headers,
    ).json()["id"]

    # 先以匿名身份填充公共缓存，不能污染登录用户的状态。
    assert client.get(f"/api/v1/questions/{qid}/answers").json()[0]["is_liked"] is False
    client.post(f"/api/v1/like/{answer_id}", headers=headers)

    liked = client.get(f"/api/v1/questions/{qid}/answers", headers=headers).json()[0]
    anonymous = client.get(f"/api/v1/questions/{qid}/answers").json()[0]
    assert liked["is_liked"] is True
    assert anonymous["is_liked"] is False

    client.delete(f"/api/v1/like/{answer_id}", headers=headers)
    assert client.get(f"/api/v1/questions/{qid}/answers", headers=headers).json()[0]["is_liked"] is False


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
