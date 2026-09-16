import hashlib
import json
import os
import re
import threading
from typing import List, Dict

# 模型下载至到本地缓存
os.environ["HF_HUB_OFFLINE"] = "1"

import jieba
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from app.core.config import BASE_DIR
from app.core.redis_client import redis_client

_SIMILARITY_THRESHOLD = 0.05  # 重排分数阈值：bge-reranker 输出相对排序分，15 条库实测相关~0.2、无关~0；曾下调到 0 导致库外无关题全部误伤（防幻觉破坏），恢复 0.05
_RETRIEVAL_TOP_K = 50  # 第一路召回数量
_RERANK_TOP_K = 8  # 精排后保留数量
_RRF_FUSION_N = 40  # 两路召回 RRF 融合后送入精排的候选数
# 快慢双路判定阈值：向量检索 top-1 余弦分高于该值时，直接信任向量排名，跳过重排
_FAST_PATH_TOP_SCORE = 0.7
# 检索结果缓存 TTL（秒）：同一 query 在窗口期内复用命中文档，避免重复耗时精排。
_RAG_CACHE_TTL = 1800
_RAG_INDEX_VERSION_KEY = "rag:index:version"

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    encode_kwargs={"normalize_embeddings": True},
)

vectorstore = Chroma(
    collection_name="qa_docs",
    embedding_function=embeddings,
    # 基于项目根定位持久化目录，避免依赖当前工作目录
    persist_directory=str(BASE_DIR / "chroma_db"),
)

# cross-encoder 精排模型
reranker = CrossEncoder(
    model_name_or_path=str(BASE_DIR / "models" / "bge-reranker")
)


def embed(texts: List[str]) -> list[list[float]]:
    """将文本转为向量（归一化）。"""
    return embeddings.embed_documents(texts)


# ===== BM25 关键词召回（字面路，与向量语义路互补）=====
# 纯内存索引：内容跟随向量库，应用启动时懒加载、sync_kb_incremental 跑完后重建。
# 重建只数一遍词频（无 embedding、无网络，1 万条秒级），所以不做增量维护。
_bm25_index = None
_bm25_docs: List[Dict] = []
_bm25_lock = threading.RLock()

_CJK_ALNUM = re.compile(r"[一-龥a-zA-Z0-9]")


def _tokenize(text: str) -> list[str]:
    """jieba 中文分词，过滤纯标点 token。中文无空格分隔，BM25 必须先分词才能按词统计。"""
    return [tok for tok in jieba.cut(text) if _CJK_ALNUM.search(tok)]


def build_bm25_index() -> int:
    """从 Chroma 现有文档构建内存 BM25 索引，返回索引条数。
    与向量库共用同一份文档原文（vectorstore.get()），不重新读库、不重新 embedding。
    """
    global _bm25_index, _bm25_docs
    stored = vectorstore.get(include=["documents", "metadatas"])
    texts = stored.get("documents", [])
    metas = stored.get("metadatas", [])
    docs = [
        {"content": text, "source": meta or {}}
        for text, meta in zip(texts, metas)
    ]
    index = BM25Okapi([_tokenize(t) for t in texts]) if texts else None
    # 先在局部变量完成耗时构建，再一次替换，查询不会读到半成品。
    with _bm25_lock:
        _bm25_docs = docs
        _bm25_index = index
    return len(docs)


def bm25_search(query: str, top_k: int = 50) -> List[Dict]:
    """BM25 关键词召回，返回与向量检索相同结构的 hits（含 content/source）。索引未建时懒加载。"""
    global _bm25_index
    if _bm25_index is None:
        build_bm25_index()
    with _bm25_lock:
        index, docs = _bm25_index, list(_bm25_docs)
    if index is None:
        return []
    scores = index.get_scores(_tokenize(query))
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [docs[i] for i in order[:top_k] if scores[i] > 0]


def _rrf_fusion(ranked_lists: List[List[Dict]], top_n: int, k: int = 60) -> List[Dict]:
    """RRF（Reciprocal Rank Fusion）多路召回融合。

    每路召回按名次计 1/(k+rank) 分，多路同现累加，按融合分降序取 top_n。
    按内容指纹去重（同内容多副本只保留一份），融合只决定「把谁送进精排」，最终排序交给 cross-encoder。
    """
    fused: Dict[str, float] = {}
    hits_by_key: Dict[str, Dict] = {}
    for hits in ranked_lists:
        for rank, hit in enumerate(hits, start=1):
            key = hashlib.md5(hit.get("content", "").encode("utf-8")).hexdigest()
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank)
            hits_by_key.setdefault(key, hit)
    ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    return [hits_by_key[key] for key, _ in ordered[:top_n]]


def _norm(query: str) -> str:
    """归一化查询：去掉所有空格 + 统一小写，让 "JWT过期" / "JWT 过期" 视为同一 query。"""
    return query.replace(" ", "").lower()


def _cache_key(query: str) -> str:
    """归一化查询并生成缓存 key。"""
    return f"rag:search:{rag_index_version()}:{_norm(query)}"


def rag_index_version() -> str:
    """当前知识库版本；版本变更后旧检索缓存自然不再命中。"""
    return redis_client.get(_RAG_INDEX_VERSION_KEY) or "0"


def invalidate_rag_cache() -> int:
    """在知识库文档变化后推进版本，避免扫描并删除所有历史缓存键。"""
    return int(redis_client.incr(_RAG_INDEX_VERSION_KEY))


def _cache_get(query: str):
    """读检索结果缓存；未命中返回 None。"""
    data = redis_client.get(_cache_key(query))
    return json.loads(data) if data else None


def _cache_set(query: str, hits: List[Dict]) -> None:
    """写检索结果缓存。"""
    redis_client.setex(
        _cache_key(query), _RAG_CACHE_TTL, json.dumps(hits, ensure_ascii=False)
    )


def search(query: str, top_k: int = _RERANK_TOP_K, use_bm25: bool = True) -> List[Dict]:
    # 精确命中：同一 query 直接复用，零成本
    cached = _cache_get(query)
    if cached is not None:
        return cached

    # 向量召回，余弦分数若大于阈值直接返回
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
        # 慢路：向量（可选叠加 BM25）经 RRF 融合压缩后，cross-encoder 逐字比对精排
        vector_hits = [
            {"content": doc.page_content, "source": doc.metadata}
            for doc, _ in scored_docs
        ]
        if use_bm25:
            bm25_hits = bm25_search(query, top_k=_RETRIEVAL_TOP_K)
            candidates = _rrf_fusion([vector_hits, bm25_hits], top_n=_RRF_FUSION_N)
        else:
            candidates = vector_hits
        scores = reranker.predict([(query, d["content"]) for d in candidates])
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        hits = []
        for doc, score in ranked[:top_k]:
            # 精排分数低于阈值视为噪音直接丢弃
            if score > _SIMILARITY_THRESHOLD:
                hits.append(doc)

    _cache_set(query, hits)
    return hits


def format_context(hits: List[Dict], top_k: int = 3) -> str:
    """把检索命中的资料格式化成带编号、带来源、带 qid 的结构化文本，供 LLM 引用。
    每条资料输出一块：[资料N] 来源：{title} (qid:{id})，随后换行接正文。hits 已按相关度降序排列，这里只取前 top_k 条且不重排，把最相关的资料放在最前，落在 LLM注意力最强的位置；保留来源标题是为了让 LLM 引用资料时能标注出处，qid 供 get_answers 工具查询该问题回答使用。
    Context Formatting and avoid Lost-in-the-Middle
    """
    blocks = []
    for i, hit in enumerate(hits[:top_k], start=1):
        source = hit.get("source") or {}
        if isinstance(source, dict):
            title = source.get("title", "")
            qid = source.get("qid")
        else:
            title = str(source)
            qid = None
        head = f"[资料{i}] 来源：{title}"
        if qid is not None:
            head += f" (qid:{qid})"
        blocks.append(f"{head}\n{hit.get('content', '')}")
    return "\n\n".join(blocks)
