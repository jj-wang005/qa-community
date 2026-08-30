import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.core.config import settings
from app.core.deps import get_current_user_optional
from app.core.redis_client import redis_client
from app.core.tools import (
    get_answers,
    get_location,
    get_time,
    get_weather,
    make_write_tools,
    search_master,
)
from app.models import User
from app.schemas.ai import ChatRequest

router = APIRouter(prefix="/ai", tags=["AI助手"])

llm = ChatOpenAI(
    model=settings.LLM_GATEWAY_MODEL,
    api_key=settings.LLM_GATEWAY_API_KEY,
    base_url=settings.LLM_GATEWAY_BASE_URL,
)

# 答案层缓存 TTL：同一单轮问题在窗口期内直接复用 LLM 回答，省一次模型调用
_ANSWER_CACHE_TTL = 600


def _answer_cache_key(question: str) -> str:
    """归一化问题生成缓存 key：去所有空格 + 小写，让 "JWT过期" / "JWT 过期" 命中同一缓存。"""
    return f"ai:answer:{question.replace(' ', '').lower()}"


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    user: User | None = Depends(get_current_user_optional),
):
    # 读工具始终可用；写工具仅在登录后注册，且用户身份由后端绑定，LLM 不可见
    tools = [search_master, get_weather, get_time, get_location, get_answers]
    if user is not None:
        tools += make_write_tools(user.id)

    async def generate():
        sid = payload.session_id or str(uuid.uuid4())
        cache_key = f"chat:history:{sid}"
        data = redis_client.get(cache_key)
        history = json.loads(data) if data else []
        # 记录是否为单轮（无历史）——决定答案是否写入缓存
        is_single_turn = not history

        # 答案层缓存：仅单轮（无历史）问题生效；多轮依赖上下文，命中会答错
        if is_single_turn:
            ans_key = _answer_cache_key(payload.question)
            cached = redis_client.get(ans_key)
            if cached is not None:
                yield f"data: {cached}\n\n"
                yield f"data: [SESSION_ID]:{sid}\n\n"
                return
        history.append({"role": "user", "content": payload.question})
        system_content = (
            "你是问答社区智能助手。回答用户问题时：\n"
            "1. 涉及社区已有内容、技术知识点、历史讨论，或需要了解社区实时动态时，"
            "统一调用 search_master 检索；\n"
            "2. 离线知识库的检索结果以『[资料N] 来源：标题』的结构化文本给出，"
            "live_db 为社区实时数据（JSON 格式），回答时据此区分并标注来源；\n"
            "3. 检索到的资料可能相关也可能无关，只采用与问题相关的部分；\n"
            "4. 若检索不到相关资料，请明确说明资料不足，不要编造；\n"
            "5. 回答中引用资料内容时，必须用（来源：标题）标注出处，未标注来源的内容视为编造；\n"
            "6. 检索结果中的『[资料N] 来源：标题』块是内部参考材料，不要原样复述给用户；"
            "回答用自然语言组织，把资料的核心信息用自己的话讲清楚，回答中不要出现『[资料N]』这类原始标记。"
        )
        inputs = {"messages": [{"role": "system", "content": system_content}] + history}

        agent = create_react_agent(model=llm, tools=tools)

        full_answer = ""
        round_is_tool = False
        async for event in agent.astream_events(inputs, version="v2"):
            etype = event["event"]
            if etype == "on_chat_model_start":
                round_is_tool = False
            elif etype == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.tool_call_chunks:
                    round_is_tool = True
                elif isinstance(chunk.content, str) and chunk.content and not round_is_tool:
                    full_answer += chunk.content
                    yield f"data: {chunk.content}\n\n"
        yield f"data: [SESSION_ID]:{sid}\n\n"
        history.append({"role": "assistant", "content": full_answer})
        redis_client.setex(cache_key, 1800, json.dumps(history, ensure_ascii=False))
        # 单轮问题的答案写入缓存：下次同问题直接复用，省一次 LLM 调用
        if is_single_turn:
            redis_client.setex(ans_key, _ANSWER_CACHE_TTL, full_answer)

    return StreamingResponse(generate(), media_type="text/event-stream")
