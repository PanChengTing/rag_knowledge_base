from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus
from app.db.repositories.chunk_repo import _permission_where
class DocumentRepository:
    def __init__(self,session:AsyncSession)->None:
        self.session = session

    async def get_by_id(self,document_id:UUID,*,permission_tags:list[str]|None = None)->Document|None:
        if permission_tags is None:
            return await self.session.get(Document,document_id)
        perm_where = _permission_where(permission_tags)
        stmt = select(Document).where(Document.id == document_id)
        if perm_where is not None:
            stmt = stmt.where(perm_where)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_hash(self,file_hash:str)->Document|None:
        stmt = select(Document).where(Document.file_hash==file_hash)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add(self,document:Document)->Document:
        self.session.add(document)
        await self.session.flush()
        return document

    async def update_status(
            self,
            document_id:UUID,
            status:DocumentStatus,
            *,
            error_message:str|None = None,
    )->None:
        doc = await self.get_by_id(document_id)
        if doc is None:
            return
        doc.status = status
        if error_message is not None or status!=DocumentStatus.FAILED:
            doc.error_message = error_message

    #返回分页的文档
    async def list_paginated(
            self,
            page:int,
            page_size:int,
            *,
            status:DocumentStatus|None=None,
            permission_tags:list[str]|None = None
    ) ->tuple[list[Document],int]:
        offset = (page-1)*page_size
        #获取当页内容
        item_stmt = (
            select(Document).order_by(Document.created_at.desc())
            .offset(offset).limit(page_size)
        )
        #计算符合条件的所有文档
        count_stmt = select(func.count()).select_from(Document)
        if status is not None:
            item_stmt = item_stmt.where(Document.status==status)
            count_stmt = count_stmt.where(Document.status==status)
        perm_where = _permission_where(permission_tags)
        if perm_where is not None:
            item_stmt = item_stmt.where(perm_where)
            count_stmt  = count_stmt.where(perm_where)
        #scarlars.all获取多条记录，并将其合并成一个列表
        items = (await self.session.execute(item_stmt)).scalars().all()
        #scarlar_one,取出一行中的唯一统计结果，如果查询结果不唯一会报错
        total = (await self.session.execute(count_stmt)).scalar_one()
        return list(items),int(total)

    async def delete(self,document:Document)->None:
        await self.session.delete(document)