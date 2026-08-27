import os
from typing import List, Dict

# 模型下载至到本地缓存
os.environ["HF_HUB_OFFLINE"] = "1"

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import CrossEncoder

_SIMILARITY_THRESHOLD = 0.4  # 相似度阈值
_RETRIEVAL_TOP_K = 20  # 第一路召回数量
_RERANK_TOP_K = 5  # 精排后保留数量

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


def search(query: str, top_k: int = _RERANK_TOP_K) -> List[Dict]:
    # 向量召回
    docs = vectorstore.similarity_search(query, k=_RETRIEVAL_TOP_K)
    if not docs:
        return []

    # cross-encoder 精排，把 query 与每个候选拼成一对逐字比对
    scores = reranker.predict([(query, doc.page_content) for doc in docs])
    ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)

    hits = []
    for doc, score in ranked[:top_k]:
        if score > _SIMILARITY_THRESHOLD:
            hits.append({"content": doc.page_content, "source": doc.metadata})
    return hits
