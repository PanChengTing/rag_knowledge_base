from app.workflows.rag_state import RAGState
from app.core.config import settings
from app.llm.reranker import get_reranker

async def rerank(state:RAGState)->RAGState:
    chunks = state.get("retrieved_chunks",[])
    if not settings.rerank_enabled or len(chunks)<=1:
        return {}
    reranked =await get_reranker().rerank(state["query"],chunks)
    #虽然对所有检索出来的文档都进行了精排，最后只返回前几个
    return {"retrieved_chunks":reranked[:settings.retrieval_top_k]}