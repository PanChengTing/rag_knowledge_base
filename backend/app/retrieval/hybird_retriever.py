import asyncio
from uuid import UUID

from langsmith import traceable

from app.core.log_config import get_logger
from app.retrieval.vector_retriever import KeywordRetriever, RetrievedChunk, VectorRetriever
from app.db.session import AsyncSessionLocal
from app.core.config import settings


logger = get_logger(__name__)
#计算单个文档的向量排名分数
def _with_vector(hit:RetrievedChunk,*,rank:int,k:int) ->RetrievedChunk:
    rrf_score=1.0/(k+rank)
    return RetrievedChunk(
        chunk_id=hit.chunk_id,
        document_id=hit.document_id,
        document_name=hit.document_name,
        content=hit.content,
        page_no=hit.page_no,
        section_path=hit.section_path,
        score=rrf_score,
        sources=("vector",),
        vector_rank=rank,
        vector_score=hit.vector_score,
        rrf_score=rrf_score,
    )
#计算单个文档的关键词排名分数
def _with_keyword(hit:RetrievedChunk,*,rank:int,k:int) ->RetrievedChunk:
    rrf_score=1.0/(k+rank)
    return RetrievedChunk(
        chunk_id=hit.chunk_id,
        document_id=hit.document_id,
        document_name=hit.document_name,
        content=hit.content,
        page_no=hit.page_no,
        section_path=hit.section_path,
        score=rrf_score,
        sources=("keyword",),
        keyword_rank=rank,
        keyword_score=hit.keyword_score,
        rrf_score=rrf_score,
    )

#两路计算结果合并起来
def _merge_keyword_into(
        existing:RetrievedChunk,
        keyword_hit:RetrievedChunk,
        *,
        rank:int,
        k:int,
)->RetrievedChunk:
    new_rrf = (existing.rrf_score or 0.0) + 1.0/(k+rank)
    return RetrievedChunk(
        chunk_id=existing.chunk_id,
        document_id=existing.document_id,
        document_name=existing.document_name,
        content=existing.content,
        page_no=existing.page_no,
        section_path=existing.page_no,
        score=new_rrf,
        sources=("vector","keyword"),
        vector_rank=existing.vector_rank,
        vector_score=existing.vector_score,
        keyword_score=keyword_hit.keyword_score,
        keyword_rank=rank,
        rrf_score=new_rrf,
    )

def rrf_fuse(
    vector_hits:list[RetrievedChunk],
    keyword_hits:list[RetrievedChunk],
    *,
    k:int,
    top_k:int,    
)->list[RetrievedChunk]:
    by_id:dict[UUID,RetrievedChunk] ={}
    for rank,hit in enumerate(vector_hits,start=1):
        by_id[hit.chunk_id] = _with_vector(hit,rank=rank,k=k)
    for rank,hit in enumerate(keyword_hits,start=1):
        existing= by_id.get(hit.chunk_id)
        if existing is None:
            by_id[hit.chunk_id] = _with_keyword(hit,rank=rank,k=k)
        else:
            by_id[hit.chunk_id] = _merge_keyword_into(existing,hit,rank=rank,k=k)

    fused = sorted(
        by_id.values(),
        key=lambda c:c.rrf_score or 0.0,
        reverse=True
    )
    return fused[:top_k]
    
class HybridRetriever:
    @traceable(name="HybridRetriever.search",run_type="retriever")
    async def search(
        self,
        query:str,
        *,
        recall_top_k:int,
        final_top_k:int
    )->list[RetrievedChunk]:
        vector_hits,keyword_hits = await asyncio.gather(
            self._safe_search(VectorRetriever,query,recall_top_k,"vector"),
            self._safe_search(KeywordRetriever,query,recall_top_k,"keyword")
        )
        return rrf_fuse(
            vector_hits=vector_hits,
            keyword_hits=keyword_hits,
            k =settings.rrf_k,
            top_k=final_top_k,
        )


    #兜底方案，rrffuse不起作用，会用这个
    @staticmethod
    async def _safe_search(
            retriever_cls:type[VectorRetriever]|type[KeywordRetriever],
            query:str,
            top_k:int,
            label:str,
    )->list[RetrievedChunk]:
        try:
            async with AsyncSessionLocal() as session:
                retriever = retriever_cls(session)
                return await retriever.search(query,top_k)
        except Exception:
            logger.exception("hybrid retrieve %s 路异常，降级为空结果",label)
            return []