import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.core.config import settings
from app.core.deps import get_current_user_optional
from app.core.redis import redis_client
from app.core.tools import (
    get_answers,
    get_location,
    get_time,
    get_weather,
    make_write_tools,
    search_kb,
    search_question,
)
from app.models import User
from app.schemas.ai import ChatRequest

router = APIRouter(prefix="/ai", tags=["AI助手"])

llm = ChatOpenAI(
    model="mimo-v2.5",
    api_key=settings.XIAOMI_MIMO_API_KEY,
    base_url="https://api.xiaomimimo.com/v1",
)


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    user: User | None = Depends(get_current_user_optional),
):
    # 读工具始终可用；写工具仅在登录后注册，且用户身份由后端绑定，LLM 不可见
    tools = [search_question, search_kb, get_weather, get_time, get_location, get_answers]
    if user is not None:
        tools += make_write_tools(user.id)

    async def generate():
        sid = payload.session_id or str(uuid.uuid4())
        cache_key = f"chat:history:{sid}"
        data = redis_client.get(cache_key)
        history = json.loads(data) if data else []
        history.append({"role": "user", "content": payload.question})
        system_content = (
            "你是问答社区智能助手。回答用户问题时：\n"
            "1. 涉及社区已有内容、技术知识点时，先调用 search_kb 检索离线知识库，"
            "或调用 search_question 查询社区实时数据；\n"
            "2. 检索到的资料可能相关也可能无关，只采用与问题相关的部分，并标注来源；\n"
            "3. 若检索不到相关资料，请明确说明资料不足，不要编造。"
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

    return StreamingResponse(generate(), media_type="text/event-stream")
