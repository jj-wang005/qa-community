import json
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.rag import search, build_prompt
from app.core.redis import redis_client
from app.schemas.ai import ChatRequest

router = APIRouter(prefix="/ai", tags=["AI助手"])
client = AsyncOpenAI(
    api_key=settings.XIAOMI_MIMO_API_KEY,
    # base_url="https://api.deepseek.com",
    base_url="https://api.xiaomimimo.com/v1"
)


@router.post("/chat")
async def chat(payload: ChatRequest):
    async def generate():
        sid = payload.session_id or str(uuid.uuid4())
        cache_key = f"chat:history:{sid}"
        data = redis_client.get(cache_key)
        history = json.loads(data) if data else []
        history.append({"role": "user", "content": payload.question})
        hits = search(payload.question)
        system_content = build_prompt(hits)
        messages = [{"role": "system", "content": system_content}] + history
        stream = await client.chat.completions.create(
            model="mimo-v2.5",
            messages= messages,
            stream=True,
        )
        full_answer = ""
        async for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                full_answer += content
                yield f"data: {content}\n\n"
        yield f"data: [SESSION_ID]:{sid}\n\n"
        history.append({"role": "assistant", "content": full_answer})
        redis_client.setex(cache_key, 1800, json.dumps(history, ensure_ascii=False))

    return StreamingResponse(generate(), media_type="text/event-stream")