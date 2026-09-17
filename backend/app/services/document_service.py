

import hashlib
from pathlib import PurePath
from uuid import UUID
from fastapi import BackgroundTasks, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models import Document, DocumentChunk, DocumentStatus
from app.core.log_config import get_logger
from app.storage.file_service import FileService, get_file_service
from app.db.repositories.document_repo import DocumentRepository
from app.db.repositories.chunk_repo import ChunkStats, DocumentChunkRepository
from app.core.config import settings
from app.ingestion.pipeline import ingest_document

#MIME类型和后缀名的映射关系
_ACCEPTED_MIME_TYPES:dict[str,str] ={
    "application/pdf":".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":".docx",
    "text/markdown":".md",
    "text/x-markdown":".md",
    "text/html":".html",
    "application/xhtml+xml":".html",
}

#后缀和MIME类型的映射
_ACCEPTED_SUFFIXES:dict[str,str] = {
    ".pdf":"application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md":"text/markdown",
    ".markdown":"text/markdown",
    ".html":"text/html",
    ".htm":"text/html",
}

#允许删除的文件状态
_DELETEABLE_STATUS = frozenset(
    {DocumentStatus.READY,DocumentStatus.FAILED,DocumentStatus.UPLOADING}
)

#靠文件后缀名和浏览器给出的文件类型一起判断文件类型，后缀名的优先级更高
def _resolve_mime_and_suffix(file:UploadFile)->tuple[str,str]:
    suffix = PurePath(file.filename or "").suffix.lower()
    if suffix in _ACCEPTED_SUFFIXES:
        return _ACCEPTED_SUFFIXES[suffix],suffix

    mime = file.content_type or ""
    if mime in _ACCEPTED_MIME_TYPES:
        return mime,_ACCEPTED_MIME_TYPES[mime]

    raise ValidationError(
        f"不支持的文件类型：{file.filename}（{mime or '未知'}）。"
        "当前仅支持PDF DOCX  MARKDOWN HTML"
    )

logger = get_logger(__name__)
class DocumentService:
    def __init__(self,session:AsyncSession,file_service:FileService|None = None)->None:
        self.session = session
        self.repo = DocumentRepository(session)
        self.chunk_repo = DocumentChunkRepository(session)
        self.file_service = file_service or get_file_service()

    #上传文档，接收一个类型为UploadFile的文件
    async def upload(self,file:UploadFile,background_tasks:BackgroundTasks)->Document:
        mime_type,suffix = _resolve_mime_and_suffix(file)

        content = await file.read()
        max_bytges = settings.upload_max_size_mb*1024*1024
        if len(content)==0:
            raise ValidationError("上传文件为空")
        if len(content) > max_bytges:
            raise ValidationError(f"文件超过{settings.upload_max_size_mb}MB 上限")

        file_hash = hashlib.sha256(content).hexdigest()

        existing = await self.repo.get_by_hash(file_hash)
        if existing is not None:
            logger.info("file hash hit,reuse document:%s",existing.id)
            return existing

        #把文档上传到COS库
        object_key = await self.file_service.upload(
            content=content,
            file_hash=file_hash,
            suffix=suffix,
            mine_type=mime_type,
        )

        #创建一个Document数据
        document = Document(
            name = file.filename or f"{file_hash}{suffix}",
            file_hash = file_hash,
            mime_type = mime_type,
            size=len(content),
            storage_provider="cos",
            cos_bucket = self.file_service.bucket,
            cos_object_key = object_key,
            cos_region = self.file_service.region,
            status = DocumentStatus.UPLOADING,
        )

        await self.repo.add(document)
        await self.session.commit()
        await self.session.refresh(document)

        #从COS文档中下载文档，并且拆分文档转换为向量，但是放在后台任务中执行
        background_tasks.add_task(ingest_document,document.id)

        return document

    #获取文档
    async def get(self,document_id:UUID) -> Document:
        doc = await self.repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError("文档不存在")
        return doc

    #分页获取文档
    async def list_documents(
            self,
            page:int,
            page_size:int,
            *,
            status:DocumentStatus|None = None,
    ) ->tuple[list[Document],int]:
        return await self.repo.list_paginated(page,page_size,status=status)

    #删除文档，先删除DB，再删除COS
    async def delete(self,document_id:UUID) ->None:
        doc = await self.repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError("文档不存在")

        if doc.status not in _DELETEABLE_STATUS:
            raise ValidationError("文档处理中，请等待完成或失败后再删除")

        object_key = doc.cos_object_key
        await self.repo.delete(doc)
        await self.session.commit()

        await self.file_service.delete(object_key)
        logger.info("document deleted:id =%s",document_id)

    #重试
    async def retry(self,document_id:UUID,background_tasks:BackgroundTasks) ->None:
        doc = await self.repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError("文档不存在")

        if doc.status != DocumentStatus.FAILED:
            raise ValidationError("仅失败状态的文档支持重试")

        await self.chunk_repo.delete_by_document(document_id)
        doc.status = DocumentStatus.UPLOADING
        doc.error_message = None
        await self.session.commit()
        await self.session.refresh(doc)

        #从COS文档中下载文档，并且拆分文档转换为向量，但是放在后台任务中执行
        background_tasks.add_task(ingest_document,doc.id)
        logger.info("document retry scheduled:id=%s",document_id)
        return doc

    #分页获取文档切片
    async def list_chunks(
            self,
            document_id:UUID,
            page:int,
            page_size:int,
    ) ->tuple[list[DocumentChunk],int,ChunkStats|None]:
        await self.get(document_id)
        item,total = await self.chunk_repo.list_paginated_by_document(document_id=document_id,page=page,page_size=page_size)
        stats = await self.chunk_repo.get_stats(document_id=document_id)
        return item,total,stats

    #获取文档切片
    async def get_chunk(self,document_id:UUID,chunk_id:UUID)->DocumentChunk:
        chunk = await self.chunk_repo.get_for_document(document_id,chunk_id)
        if chunk is None:
            raise NotFoundError("Chunk 不存在")
        return chunk