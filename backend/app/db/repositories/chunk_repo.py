from dataclasses import dataclass
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete,func,select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk

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