

from app.llm.query_rewriter import get_query_rewriter
from app.workflows.rag_state import RAGState
from app.core.config import settings

async def route_query(state:RAGState)->RAGState:
    """
    对用户的查询进行优化，返回优化后的查询和相关信息
    """
    if not settings.query_route_enabled:
        return {"route":"original"}
    
    result = await get_query_rewriter().optimize(
        question=state["question"],
        multi_query_count=settings.multi_query_count
    )
    #更新RAGState
    update:RAGState = {"route":result.route,"query":result.query}
    if result.rewritten_query is not None:
        update["rewritten_query"] = result.rewritten_query
    elif result.hyde_answer is not None:
        update["hyde_answer"] = result.hyde_answer
    elif result.multi_querys is not None:
        update["multi_querys"] = result.multi_querys
    return update