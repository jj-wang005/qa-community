"""
tests/test_answers.py —— 回答接口的自动化测试

覆盖：发回答（鉴权/404/成功）、answer_count 联动、回答分页、采纳、越权防护
"""


def test_post_answer_without_token_returns_401(client):
    """没带 token 发回答 → 被 get_current_user 拦下，返回 401。"""
    resp = client.post("/questions/1/answers", json={"content": "回答"})
    assert resp.status_code == 401


def test_post_answer_to_missing_question_returns_404(client, auth):
    """对不存在的帖子发回答 → 404。"""
    token = auth(username="ghost")
    resp = client.post(
        "/questions/99999/answers",
        json={"content": "回答"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_register_login_and_post_answer(client, auth):
    """注册 → 登录 → 发问题拿 qid → 带 token 发回答 → 成功。"""
    token = auth(username="poster")

    client.post(
        "/questions",
        json={"title": "第一个问题", "content": "问题的详细内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/questions?sort=new").json()[0]["id"]

    resp = client.post(
        f"/questions/{qid}/answers",
        json={"content": "这个挺不错的"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "这个挺不错的"


def test_answer_count_increments(client, auth):
    """发回答后，问题的 answer_count 应该 +1（数据联动）。"""
    token = auth(username="counter")
    client.post(
        "/questions",
        json={"title": "题", "content": "内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/questions?sort=new").json()[0]["id"]
    before = client.get(f"/questions/{qid}").json()["answer_count"]

    client.post(
        f"/questions/{qid}/answers",
        json={"content": "答"},
        headers={"Authorization": f"Bearer {token}"},
    )

    after = client.get(f"/questions/{qid}").json()["answer_count"]
    assert after == before + 1


def test_list_answers_respects_page_size(client, auth):
    """给同一个问题发 3 个回答，size=2 → 只回 2 条。

    必须造 > 每页数量的数据，分页才有东西可砍（防止「小数据量测不出分页」）。
    """
    token = auth(username="page_user")
    client.post(
        "/questions",
        json={"title": "问题0", "content": "内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/questions?sort=new").json()[0]["id"]

    for i in range(3):
        client.post(
            f"/questions/{qid}/answers",
            json={"content": f"内容{i}"},
            headers={"Authorization": f"Bearer {token}"},
        )

    resp = client.get(f"/questions/{qid}/answers?size=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_answers_accepted_only_returns_accepted(client, auth):
    """sort=accepted 时，只返回被采纳的回答。"""
    token = auth(username="accepted_user")
    client.post(
        "/questions",
        json={"title": "题", "content": "内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/questions?sort=new").json()[0]["id"]

    # 发 3 条回答，只采纳其中 1 条
    aids = []
    for i in range(3):
        aid = client.post(
            f"/questions/{qid}/answers",
            json={"content": f"回答{i}"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()["id"]
        aids.append(aid)
    client.post(f"/answers/{aids[0]}/accept", headers={"Authorization": f"Bearer {token}"})

    resp = client.get(f"/questions/{qid}/answers?sort=accepted")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == aids[0]
    assert resp.json()[0]["is_accepted"] is True


def test_list_answers_hot_sorts_accepted_first(client, auth):
    """sort=hot 时，被采纳的回答应排在前面（is_accepted 有 50 分加成）。"""
    token = auth(username="hot_user")
    client.post(
        "/questions",
        json={"title": "题", "content": "内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/questions?sort=new").json()[0]["id"]

    # 发 2 条回答：回答 A 0 赞未采纳，回答 B 0 赞但被采纳 → B 应排前面
    aid_a = client.post(
        f"/questions/{qid}/answers",
        json={"content": "A"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]
    aid_b = client.post(
        f"/questions/{qid}/answers",
        json={"content": "B"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]
    client.post(f"/answers/{aid_b}/accept", headers={"Authorization": f"Bearer {token}"})

    resp = client.get(f"/questions/{qid}/answers?sort=hot")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == aid_b


def test_register_login_and_accept_answer(client, auth):
    """发问题 → 发回答 → 采纳回答 → 成功，且采纳真的生效。"""
    token = auth(username="accepter")
    client.post(
        "/questions",
        json={"title": "第一个问题", "content": "问题的详细内容"},
        headers={"Authorization": f"Bearer {token}"},
    )
    qid = client.get("/questions?sort=new").json()[0]["id"]

    resp = client.post(
        f"/questions/{qid}/answers",
        json={"content": "这个挺不错的"},
        headers={"Authorization": f"Bearer {token}"},
    )
    aid = resp.json()["id"]

    resp = client.post(
        f"/answers/{aid}/accept",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["接受"] is True


def test_cannot_accept_others_answer(client, auth):
    """用户 B 不能采纳用户 A 的回答 → 403（越权防护）。"""
    token_a = auth(username="user_a")
    client.post(
        "/questions",
        json={"title": "A 的题", "content": "内容"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    qid = client.get("/questions?sort=new").json()[0]["id"]
    aid = client.post(
        f"/questions/{qid}/answers",
        json={"content": "A 的回答"},
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()["id"]

    token_b = auth(username="user_b")
    resp = client.post(
        f"/answers/{aid}/accept",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403
