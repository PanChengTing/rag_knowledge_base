import dataclasses
from typing import Any

import httpx
from langsmith import traceable

from app.core.log_config import get_logger
from app.core.config import settings
from app.retrieval.vector_retriever import RetrievedChunk

logger = get_logger(__name__)
class Reranker:
    def __init__(self):
        self._client:httpx.AsyncClient|None =None

    def _get_client(self)->httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=settings.rerank_timeout)
        return self._client
    @traceable(name="Reranker.rerank",run_type="tool")
    #主函数，输入问题及候选答案，输出排序好的候选答案及分数
    async def rerank(
            self,query:str,candidates:list[RetrievedChunk]
    )->list[RetrievedChunk]:
        if len(candidates)<=1:
            return candidates

        api_key = settings.effective_rerank_api_key
        if not api_key:
            raise ConnectionError(
                "Rerank API key 未配置，请设置RERANK_API_KEY 或CHAT_API_KEY"
            )

        try:
            scores = await self._fetch_scores(query,candidates,api_key)
        except Exception:
            logger.exception("rerank调用失败，降级为不重排:query=%r",query)
            return candidates

        ranked = [
            dataclasses.replace(chunk,rerank_score=score)
            for chunk,score in zip(candidates,scores,strict=False)
        ]
        ranked.sort(key=lambda c:c.rerank_score or 0.0,reverse=True)
        return ranked

    #返回的是原先顺序的分数，还没有排序号
    async def _fetch_scores(
            self,query:str,candidates:list[RetrievedChunk],api_key:str
    )->list[float]:
        payload:dict[str,Any] ={
            "model":settings.rerank_model,
            "query":query,
            "documents":[c.content for c in candidates],
            "top_n":len(candidates),
        }
        headers = {
            "Authorization":f"Bearer {api_key}",
            "Content-Type":"appliction/json"
        }

        client = self._get_client()
        response = await client.post(
            settings.rerank_base_url,json=payload,headers=headers
        )
        response.raise_for_status()
        data = response.json()
        #result已经排序好了，从高到低，index里面有原来的顺序
        results= data.get("results") or []
        if not isinstance(results,list) or len(results)==0:
            raise ValueError(f"rerank响应缺少results：{data!r}")
        #重新把顺序恢复成输入之前
        scores:list[float] = [0.0] * len(candidates)
        for items in results:
            idx = items.get("index")
            score = items.get("relevance_score")
            if not isinstance(idx,int) or not isinstance(score,int|float):
                continue
            if 0<=idx<len(scores):
                scores[idx] = float(score)
        return scores

_reranker:Reranker|None = None
def get_reranker()->Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker