from dataclasses import dataclass, field
from uuid import UUID
from langsmith import traceable
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.chunk_repo import DocumentChunkRepository 
from app.ingestion.embedder import get_embeddings


@dataclass(frozen =True)
class RetrievedChunk:
    chunk_id:UUID
    document_id:UUID
    document_name:UUID
    content:str
    page_no:int|None
    section_path:str|None
    score:float
    #分成两路分数，关键词路和向量路，最终会得出混合分数
    #如果启用混合检索，score和RRF_score的分数会一样
    #sources判断有哪些路起作用了
    sources:tuple[str,...]= field(default_factory=tuple)
    vector_rank:int|None = None
    vector_score:float|None = None
    keyword_rank:int|None = None
    keyword_score:float|None =None
    rrf_score:float|None=None
    rerank_score:float|None =None

class VectorRetriever:
    def __init__(self,session:AsyncSession) ->None:
        self.chunk_repo = DocumentChunkRepository(session)
    @traceable(name="VectorRetriever.search",run_type="retriever")
    #对问题向量化，然后从数据库中找到相近的文档
    async def search(self,query:str,top_k:int)->list[RetrievedChunk]:
        embedding = await get_embeddings().aembed_query(query)
        rows = await self.chunk_repo.vector_search(embedding,top_k=top_k)
        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=chunk.document.name,
                content=chunk.content,
                page_no=chunk.page_no,
                section_path=chunk.section_path,
                # cosine_distance[0,2] 归一化为[-1,1] 数值越大越相似
                score=1.0-distance,
                sources=("vector",),
                vector_rank=rank,
                vector_score=1.0-distance,
            )
            for rank,(chunk,distance) in enumerate(rows,start=1)
        ]

class KeywordRetriever:
    def __init__(self,session:AsyncSession) ->None:
        self.chunk_repo = DocumentChunkRepository(session)
    @traceable(name="KeywordRetriever.search",run_type="retriever")
    #对问题向量化，然后从数据库中找到相近的文档
    async def search(self,query:str,top_k:int)->list[RetrievedChunk]:
        rows = await self.chunk_repo.keyword_search(query,top_k)
        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=chunk.document.name,
                content=chunk.content,
                page_no=chunk.page_no,
                section_path=chunk.section_path,
                # ts_rank没有上界，直接输出
                score=ts_rank,
                sources=("keyword",),
                vector_rank=rank,
                vector_score=ts_rank,
            )
            for rank,(chunk,ts_rank) in enumerate(rows,start=1)
        ]