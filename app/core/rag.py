import json
import os
from typing import List, Dict

# 模型下载至到本地缓存
os.environ["HF_HUB_OFFLINE"] = "1"

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import CrossEncoder

from app.core.redis import redis_client

_SIMILARITY_THRESHOLD = 0.05  # 重排分数阈值：bge-reranker 输出相对排序分，实测为：相关~0.2、无关~0
_RETRIEVAL_TOP_K = 20  # 第一路召回数量
_RERANK_TOP_K = 5  # 精排后保留数量

# 快慢双路判定阈值：向量检索 top-1 余弦分高于该值时，直接信任向量排名，跳过重排
_FAST_PATH_TOP_SCORE = 0.7
# 检索结果缓存 TTL（秒）：同一 query 在窗口期内复用命中文档，避免重复耗时精排
_RAG_CACHE_TTL = 600

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    encode_kwargs={"normalize_embeddings": True},
)

vectorstore = Chroma(
    collection_name="qa_docs",
    embedding_function=embeddings,
    persist_directory="./chroma_db",
)

# cross-encoder 精排模型
reranker = CrossEncoder(
    model_name_or_path=r"F:\python_code(1)\fastapi_projrct\qa_community\models\bge-reranker"
)


def embed(texts: List[str]) -> list[list[float]]:
    """将文本转为向量（归一化）。"""
    return embeddings.embed_documents(texts)


def _cache_key(query: str) -> str:
    """归一化询问并生成缓存 key：去掉所有空格 + 统一小写，让 "JWT过期" / "JWT 过期" 命中同一缓存。"""
    return f"rag:search:{query.replace(' ', '').lower()}"


def _cache_get(query: str):
    """读检索结果缓存；未命中返回 None。"""
    data = redis_client.get(_cache_key(query))
    return json.loads(data) if data else None


def _cache_set(query: str, hits: List[Dict]) -> None:
    """写检索结果缓存。"""
    redis_client.setex(
        _cache_key(query), _RAG_CACHE_TTL, json.dumps(hits, ensure_ascii=False)
    )


def search(query: str, top_k: int = _RERANK_TOP_K) -> List[Dict]:
    # 命中直接返回，避免重复检索
    cached = _cache_get(query)
    if cached is not None:
        return cached

    # 第一阶段：向量召回，余弦分数若大于阈值直接返回
    scored_docs = vectorstore.similarity_search_with_relevance_scores(
        query, k=_RETRIEVAL_TOP_K
    )
    if not scored_docs:
        return []

    top_score = scored_docs[0][1]
    if top_score > _FAST_PATH_TOP_SCORE:
        # 快路：向量置信度足够，信任向量排名，跳过重排
        hits = [
            {"content": doc.page_content, "source": doc.metadata}
            for doc, _ in scored_docs[:top_k]
        ]
    else:
        # 慢路：向量分值模糊，使用cross-encoder逐字比对精排
        docs = [doc for doc, _ in scored_docs]
        scores = reranker.predict([(query, doc.page_content) for doc in docs])
        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        hits = []
        for doc, score in ranked[:top_k]:
            # 精排分数低于阈值视为噪音直接丢弃
            if score > _SIMILARITY_THRESHOLD:
                hits.append({"content": doc.page_content, "source": doc.metadata})

    _cache_set(query, hits)
    return hits
