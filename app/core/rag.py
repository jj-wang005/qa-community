import json
import os
import time
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
# 检索结果缓存 TTL（秒）：同一 query 在窗口期内复用命中文档，避免重复耗时精排。
_RAG_CACHE_TTL = 1800
# 语义缓存命中阈值：当前 query 与历史 query 的向量余弦相似度超过该值，即复用其资料。
_SEMANTIC_THRESHOLD = 0.7
_SEMANTIC_INDEX_KEY = "rag:vec:index"

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


def _norm(query: str) -> str:
    """归一化查询：去掉所有空格 + 统一小写，让 "JWT过期" / "JWT 过期" 视为同一 query。"""
    return query.replace(" ", "").lower()


def _cache_key(query: str) -> str:
    """归一化查询并生成缓存 key。"""
    return f"rag:search:{_norm(query)}"


def _cache_get(query: str):
    """读检索结果缓存；未命中返回 None。"""
    data = redis_client.get(_cache_key(query))
    return json.loads(data) if data else None


def _cache_set(query: str, hits: List[Dict]) -> None:
    """写检索结果缓存。"""
    redis_client.setex(
        _cache_key(query), _RAG_CACHE_TTL, json.dumps(hits, ensure_ascii=False)
    )


def _semantic_index_set(query: str, vec) -> None:
    """把 query 向量写入语义索引，供后续换说法的 query 复用检索结果。"""
    redis_client.hset(
        _SEMANTIC_INDEX_KEY,
        _norm(query),
        json.dumps({"v": vec, "ts": time.time()}),
    )


def _semantic_lookup(vec) -> str | None:
    """在未过期的历史 query 中找与当前 query 最相似且超过阈值者，返回其归一化 query；无则 None。"""
    items = redis_client.hgetall(_SEMANTIC_INDEX_KEY)
    if not items:
        return None
    now = time.time()
    best_norm, best_sim = None, 0.0
    for norm, raw in items.items():
        item = json.loads(raw)
        if now - item["ts"] > _RAG_CACHE_TTL:
            continue  # 与 hits 同 TTL，过期项不参与比对
        sim = sum(x * y for x, y in zip(vec, item["v"]))
        if sim > _SEMANTIC_THRESHOLD and sim > best_sim:
            best_norm, best_sim = norm, sim
    return best_norm


def search(query: str, top_k: int = _RERANK_TOP_K) -> List[Dict]:
    # 精确命中：同一 query 直接复用，零成本
    cached = _cache_get(query)
    if cached is not None:
        return cached

    # 语义命中：query 换说法但语义相同，复用历史 query 的资料，跳过耗时检索
    query_vec = embed([query])[0]
    matched = _semantic_lookup(query_vec)
    if matched is not None:
        hits = _cache_get(matched)
        if hits is not None:
            return hits

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
    _semantic_index_set(query, query_vec)
    return hits
