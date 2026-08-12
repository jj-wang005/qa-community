"""
tests/test_like.py —— 点赞接口的自动化测试

点赞对象是「回答」，但它是独立的路由文件（app/routers/like.py），
所以按「一个路由文件 = 一个测试文件」的约定，单独放一个文件。
"""


def test_like_without_token_returns_401(client):
    """没带 token 点赞 → 401。"""
    resp = client.post("/like/1")
    assert resp.status_code == 401


def test_like_answer_and_duplicate(client, auth):
    """点赞成功 → 200；重复点赞 → 400（防重复逻辑）。"""
    token = auth(username="liker")
    client.post(
        "/questions",
        json={"title": "题", "content": "内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/questions?sort=new").json()[0]["id"]
    aid = client.post(
        f"/questions/{qid}/answers",
        json={"content": "答"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]

    first = client.post(f"/like/{aid}", headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 200

    second = client.post(f"/like/{aid}", headers={"Authorization": f"Bearer {token}"})
    assert second.status_code == 400
