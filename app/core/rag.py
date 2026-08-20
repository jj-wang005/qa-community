import os
from typing import List, Dict

# 模型已下载到本地缓存，强制离线加载，避免联网访问 HuggingFace 超时
os.environ["HF_HUB_OFFLINE"] = "1"

from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
client = PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("qa_docs")

_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
_DISTANCE_THRESHOLD = 1.0   # 距离阈值：超过视为不相关，直接丢弃即刻

def embed(texts:List[str]) -> list[list[float]]:
    vectors = model.encode(texts, normalize_embeddings=True) # normalize_embedding 归一化的embedding
    return vectors.tolist()

def search(query: str, top_k: int = 5) -> List[Dict]:
    query_vec = embed([_QUERY_PREFIX + query])
    result = collection.query(query_embeddings=query_vec, n_results=top_k)
    hits = []
    for doc, meta, dist in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
        if dist < _DISTANCE_THRESHOLD:
            source = meta or {}
            hits.append({"content": doc, "source": source})
    return hits

def build_prompt(hits:List[Dict]) -> str:
    if not hits:
        return ("你是问答社区智能助手。请依据你自身的知识回答用户问题。"
                "如果问题涉及本社区资料但你没有检索到，请明确说明资料不足，不要编造。")
    context = "\n\n".join(
        f"【来源：{hit['source'].get('title', '未知')}】\n{hit['content']}"
        for hit in hits
    )
    return (
        "你是问答社区智能助手。请优先依据下面检索到的社区资料回答用户问题。"
        "资料可能与问题相关也可能无关，只采用与问题相关的资料，并标注其来源；"
        "若资料不足，请明确说明，不要编造。\n\n"
        f"【检索到的资料】\n{context}"
    )
