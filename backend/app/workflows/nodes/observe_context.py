from app.retrieval.vector_retriever import RetrievedChunk
from app.core.config import settings
from app.workflows.rag_state import RAGState

#观察回答的质量，填补历史中检索文档数量，最高分数，是否满足等字段
#更新STATE中AGENT历史、循环次数、是否充足等字段
async def observe_context(state:RAGState)->RAGState:
    chunks:list[RetrievedChunk] = state.get("retrieved_chunks",[])
    sufficient = _is_sufficient(chunks)
    top_score = (
        round(chunks[0].vector_score,4)
        if chunks and chunks[0].vector_score is not None
        else None
    )
    steps = list(state.get("agent_steps",[]))
    if steps:
        last = dict(steps[-1])
        last["retrieved_count"] = len(chunks)
        last["top_score"]= top_score
        last["sufficient"] = sufficient
        steps[-1] = last
    return {
        "agent_steps":steps,
        "retrieval_round":state.get("retrieval_round",0)+1,
        "context_sufficient":sufficient
    }

def _is_sufficient(chunks:list[RetrievedChunk])->bool:
    if not chunks:
        return False
    top = chunks[0]
    if top.vector_score is None:
        return False
    return top.vector_score>=settings.retrievl_min_score