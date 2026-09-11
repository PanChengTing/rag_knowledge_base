from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.prompts import REFUSAL_ANSWER
from app.core.config import settings
from app.workflows.rag_state import RAGState
from app.retrieval.vector_retriever import RetrievedChunk, VectorRetriever
from app.retrieval.hybird_retriever import HybridRetriever

def _merge_chunks(bundles:list[list[RetrievedChunk]],top_k:int)->list[RetrievedChunk]:
    """
    将多路检索结果合并，去重，按score排序
    """
    merged:dict[str,RetrievedChunk] = {}
    #多路搜索可能命中同一个文档，保留里面分数最高的
    for bundle in bundles:
        for chunk in bundle:
            key = str(chunk.chunk_id)
            prev = merged.get(key)
            if prev is None or (chunk.rrf_score or 0.0)>(prev.rrf_score or 0.0):
                merged[key] = chunk
    ranked  = sorted(merged.values(),key=lambda x:x.rrf_score or 0.0 ,reverse=True)
    return ranked[:top_k]

def _should_refuse(chunks:list[RetrievedChunk])->bool:
    # 关键只看TOP1的语义相关度，
    # 如果TOP1没有语义相关度或者语义相关度太低，就直接拒绝
    if not chunks:
        return True
    top = chunks[0]
    if top.vector_score is None:
        return True
    return top.vector_score<settings.retrievl_min_score

#从向量数据库中搜索到对应的文档，根据文档更新答案
async def retrieve(state:RAGState)->RAGState:
    retriever = HybridRetriever()
    recall_top_k= settings.retrieval_recall_top_k
    final_top_k = settings.retrieval_top_k
    #单独处理多路查询的文档检索结果
    if state.get("route") == "multi_query" and state.get("multi_querys"):
        bundles:list[list[RetrievedChunk]] = []
        for query in state["multi_querys"] or []:
            chunks = await retriever.search(query,recall_top_k=recall_top_k,final_tok_k=final_top_k)
            bundles.append(chunks)
        chunks = _merge_chunks(bundles, final_top_k)
    else:
        chunks = await retriever.search(state["query"],recall_top_k=recall_top_k,final_tok_k=final_top_k)

    refused = _should_refuse(chunks)
    update:RAGState ={
        "retrieved_chunks":chunks,
        "refused":refused,
    }
    if refused:
        update["answer"]= REFUSAL_ANSWER
    return update
