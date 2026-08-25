import os
from typing import List, Dict

# 模型下载至到本地缓存
os.environ["HF_HUB_OFFLINE"] = "1"

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

_SIMILARITY_THRESHOLD = 0.25  # 相似度阈值：bge 余弦相似度

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    encode_kwargs={"normalize_embeddings": True},
)

vectorstore = Chroma(
    collection_name="qa_docs",
    embedding_function=embeddings,
    persist_directory="./chroma_db",
)


def embed(texts: List[str]) -> list[list[float]]:
    """将文本转为向量（归一化）。"""
    return embeddings.embed_documents(texts)


def search(query: str, top_k: int = 5) -> List[Dict]:
    """检索与问题最相关的资料，相似度不超过阈值的结果直接丢弃。"""
    docs = vectorstore.similarity_search_with_relevance_scores(query, k=top_k)
    hits = []
    for doc, score in docs:
        # bge 归一化后 relevance_score 即余弦相似度，越大越相关，<=0 视为不相关
        if score > _SIMILARITY_THRESHOLD:
            hits.append({"content": doc.page_content, "source": doc.metadata})
    return hits
