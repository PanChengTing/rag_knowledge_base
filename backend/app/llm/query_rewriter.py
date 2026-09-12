
from typing import get_args

from dataclasses import dataclass

from app.core.log_config import get_logger
from app.workflows.rag_state import QueryRoute
from app.llm.prompts import build_hyde_messages, build_multi_query_messages, build_rewrite_messages, build_route_messages
from app.llm.models import get_chat_model


logger = get_logger(__name__)

_VALID_ROUTES:tuple[str,...] = get_args(QueryRoute)

@dataclass(frozen=True)
class QueryRouteResult:
    route:QueryRoute
    query:str
    rewritten_query:str|None = None
    hyde_answer:str|None = None
    multi_querys:list[str]|None = None

def _extract_text(text:str|list[str|dict])->str:
    if isinstance(text, str):
        return text
    elif isinstance(text, list):
        return " ".join(part.get("text","") for part in text if isinstance(part, dict))
    else:
        raise ValueError(f"Unexpected type for text: {type(text)}")

class QueryRewriter:
    async def decide_route(self,question:str)->QueryRoute:
        """
        决定查询优化的策略
        """
        messages = build_route_messages(question)
        #调用LLM，返回结果 
        response = await get_chat_model().ainvoke(messages)
        raw = _extract_text(response.content).strip().lower()
        token = raw.strip("\"'`.。")
        if token in _VALID_ROUTES:
            return token
        logger.warning(f"LLM返回的查询优化策略不在预期范围内: {token},使用默认策略original")
        return "original"

    async def rewrite(self,question:str)->str:
        messages = build_rewrite_messages(question)
        response = await get_chat_model().ainvoke(messages)
        return _extract_text(response.content).strip()

    async def hyde(self,question:str)->str:
        messages = build_hyde_messages(question)
        response = await get_chat_model().ainvoke(messages)
        return _extract_text(response.content).strip()

    async def multi_query(self,question:str,n:int)->list[str]:
        messages = build_multi_query_messages(question,n)
        response = await get_chat_model().ainvoke(messages)
        text = _extract_text(response.content)
        #把问题前面的序号去掉，按行分割，取前n个
        queries = [line.strip("-*.0123456789、") for line in text.splitlines()]
        return [q for q in queries if q][:n]

    async def apply_route(self,question:str,route:QueryRoute,multi_query_count:int)->QueryRouteResult:
        # agent会直接给出route
        try:
            if route == "rewrite":
                rewritten_query = await self.rewrite(question)
                if not rewritten_query:
                    return QueryRouteResult(route="original",query=question)
                return QueryRouteResult(route="rewrite",query=rewritten_query,rewritten_query=rewritten_query)
            elif route == "hyde":
                hyde_answer = await self.hyde(question)
                if not hyde_answer:
                    return QueryRouteResult(route="original",query=question)
                return QueryRouteResult(route="hyde",query=hyde_answer,hyde_answer=hyde_answer)
            elif route == "multi_query":
                multi_querys = await self.multi_query(question,multi_query_count)
                #至少两条子查询才有意义
                if len(multi_querys)<2:
                    return QueryRouteResult(route="original",query=question)
                return QueryRouteResult(route="multi_query",query=multi_querys[0],multi_querys=multi_querys)
            else:
                return QueryRouteResult(route="original",query=question)
        except Exception as e:
            logger.error(f"查询优化失败: {e},使用默认策略original",e)
            return QueryRouteResult(route="original",query=question)

    async def optimize(self,question:str,multi_query_count:int)->QueryRouteResult:
        try:
            route = await self.decide_route(question)
        except Exception:
            logger.exception(
                "query route 判定失败，降级到original:question=%r",question
            )
            return QueryRouteResult(route='original',query=question)
        return await self.apply_route(question,route,multi_query_count)

_rewriter:QueryRewriter|None = None
def get_query_rewriter()->QueryRewriter:
    global _rewriter
    if _rewriter is None:
        _rewriter = QueryRewriter()
    return _rewriter