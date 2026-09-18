from dataclasses import dataclass
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import selectinload
from sqlalchemy import ColumnElement, and_, delete,func, or_,select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentChunk

WILDCARD_PERMISSION_TAG="*"

def _permission_where(permission_tags:list[str]|None)->ColumnElement[bool]|None:
    if permission_tags is None:
        return None
    if WILDCARD_PERMISSION_TAG in permission_tags:
        return None
    return or_(
        func.cardinality(Document.permission_tags)==0,
        Document.permission_tags.op("&&")(permission_tags)
    )

@dataclass(frozen=True)
class ChunkStats:
    total:int
    avg_length:int
    min_length:int
    max_length:int

class DocumentChunkRepository:
    def __init__(self,session:AsyncSession)->None:
        self.session = session

    async def bulk_add(self,chunks:Sequence[DocumentChunk])->None:
        if not chunks:
            return
        self.session.add_all(chunks)
        await self.session.flush()

    async def delete_by_document(self,document_id:UUID)->None:
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        return await self.session.execute(stmt)

    #返回分页的文档
    async def list_paginated_by_document(
            self,
            document_id:UUID,
            page:int,
            page_size:int,
    ) ->tuple[list[DocumentChunk],int]:
        offset = (page-1)*page_size
        #获取当页内容
        item_stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .offset(offset).limit(page_size)
        )
        #计算符合条件的所有文档
        count_stmt = (select(func.count()).select_from(DocumentChunk)
                     .where(DocumentChunk.document_id == document_id))
        #scarlars.all获取多条记录，并将其合并成一个列表
        items = (await self.session.execute(item_stmt)).scalars().all()
        #scarlar_one,取出一行中的唯一统计结果，如果查询结果不唯一会报错
        total = (await self.session.execute(count_stmt)).scalar_one()
        return list(items),int(total)

    async def get_for_document(
            self,document_id:UUID,chunk_id:UUID
            )->DocumentChunk|None:
        stmt = select(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.id == chunk_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    #计算最大长度，平均长度，最小长度
    async def get_stats(self,document_id:UUID)->ChunkStats|None:
        length = func.char_length(DocumentChunk.content)
        stmt = select(func.count().label("total"),
                      func.avg(length).label("avg_len"),
                      func.min(length).label("min_len"),
                      func.max(length).label("max_len"), ).where(DocumentChunk.document_id == document_id)

        row = (await self.session.execute(stmt)).one()
        if not row.total:
            return None
        return ChunkStats(
            total=int(row.total),
            max_length=int(row.max_len or 0),
            min_length=int(row.min_len or 0),
            avg_length=int(row.avg_len or 0),
        )

    async def vector_search(
            self,
            query_embedding:list[float],
            top_k:int,*,
            permission_tags:list[str]|None =None,
    )->list[tuple[DocumentChunk,float]]:
        #query_embedding是问题的向量
        #list是top_kd的向量切片和distance距离
        #distance是生成的一个SQL语句，计算向量之间的余弦距离，因为embedding是vector，所以提供了这个方法
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        conditions:list[ColumnElement[bool]]=[
            Document.status =="ready"
        ]
        perm_where = _permission_where(permission_tags)
        if perm_where is not None:
            conditions.append(perm_where)
        #先查询status状态为ready的文档
        #再查询属于这个文档的chunk,查询chunk的时候
        stmt = (
            select(DocumentChunk,distance.label("distance"))
            # join + where 用于筛选所属文档状态为 ready 的切片。
            .join(Document,Document.id == DocumentChunk.document_id)
            .where(and_(*conditions))
            .order_by(distance.asc())
            .limit(top_k)
            # selectinload是预加载，后续需要读chunk中的document.name，所以在这里提前加载了
            # 是把document加载到chunk.document中
            .options(selectinload(DocumentChunk.document))
        )
        rows = (await self.session.execute(stmt)).all()
        return [(chunk,float(dist)) for chunk,dist in rows]

    async def keyword_search(self,
                             query:str,
                             top_k:int,
                            permission_tags:list[str]|None =None,)->list[tuple[DocumentChunk,float]]:
    # 使用 PostgreSQL 的 chinese_zh 中文分词配置，
    # 将用户输入的普通文本转换成全文检索查询对象 tsquery。
    # plainto_tsquery 会把普通文本自动分词，并将词语按照 AND 条件连接
        tsquery =func.plainto_tsquery("chinese_zh",query)
        # 计算每个文档切片 content_tsv 与查询条件 tsquery 的相关度分数。
        # 匹配程度越高，rank 通常越大。
        #计算匹配分数
        rank_expr = func.ts_rank(DocumentChunk.content_tsv,tsquery)
        conditions:list[ColumnElement[bool]]=[
            Document.status == "ready",
            DocumentChunk.content_tsv.op("@@")(tsquery),
        ]
        perm_where = _permission_where(permission_tags)
        if perm_where is not None:
            conditions.append(perm_where)
        stmt= (
            select(DocumentChunk,rank_expr.label("rank"))
            .join(Document,Document.id == DocumentChunk.document_id)
                # @@ 是 PostgreSQL 全文检索匹配运算符。
                # 判断当前切片的 content_tsv 是否匹配 tsquery。
                #这个主要判断是否匹配    AND document_chunks.content_tsv@@ plainto_tsquery('chinese_zh', :query)
            .where(and_(*conditions))
            .order_by(rank_expr.desc())
            .limit(top_k)
            .options(selectinload(DocumentChunk.document))
        )
        rows = (await self.session.execute(stmt)).all()
        return [(chunk,float(rank)) for chunk,rank in rows]