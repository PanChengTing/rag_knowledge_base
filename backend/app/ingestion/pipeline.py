from uuid import UUID

from app.core.log_config import get_logger
from app.db.models import DocumentChunk, DocumentStatus
from app.db.repositories.chunk_repo import DocumentChunkRepository
from app.db.repositories.document_repo import DocumentRepository
from app.db.session import AsyncSessionLocal
from app.ingestion import embedder
from app.storage.file_service import get_file_service
from app.ingestion import parser
from app.ingestion import splitter

logger = get_logger(__name__)

#将文档转换成向量，并且通过设置状态，让前端可以获取到整个过程的进度
#单独使用一个事务，让状态查询可以单独执行
async def _set_status(
        document_id:UUID,
        status:DocumentStatus,
        *,
        error_message:str|None = None,
)->None:
    async with AsyncSessionLocal() as session:
        repo = DocumentRepository(session)
        await repo.update_status(document_id,status,error_message=error_message)
        await session.commit()

async def ingest_document(document_id:UUID)->None:
    logger.info("ingest start:document_id = %s",document_id)

    try:
        #从数据库中获取文档基本信息
        async with AsyncSessionLocal() as session:
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(document_id)
            if document is None:
                logger.warning("document not found,skip ingest:%s",document_id)
                return 
            object_key = document.cos_object_key
            filename = document.name

        #根据ID从COS容器中下载文档
        await _set_status(document_id,DocumentStatus.PARASING)
        content = await get_file_service().download(object_key)
        documents = await parser.parse(filename,content)

        #将文档切分成chunk
        await _set_status(document_id,DocumentStatus.INDEXING)
        chunks = splitter.split(documents)
        if not chunks:
            raise ValueError("切分后没有任何chunk,请检查文档内容")

        #将chunk转换成向量
        embeddings = await embedder.get_embeddings().aembed_documents(
            [c.page_content for c in chunks]
        )

        #将切分好的片段存在数据库里面
        async with AsyncSessionLocal() as session:
            chunk_repo = DocumentChunkRepository(session)
            await chunk_repo.bulk_add(
                [
                    DocumentChunk(
                        document_id = document_id,
                        content = c.page_content,
                        embeding = vec,
                        page_no=c.metadata.get("page_no"),
                        section_path=c.metadata.get("section_path"),
                        chunk_index = c.metadata["chunk_index"],
                        chunk_hash = c.metadata["chunk_hash"],
                        extra_metadata = c.metadata
                    )
                    for c,vec in zip(chunks,embeddings,strict=True)
                ]
            )
            await session.commit()
        await _set_status(document_id,DocumentStatus.READY,error_message=None)
        logger.info("ingest done:document_id=%s chunks=%d",document_id,len(chunks))

    except Exception as exc:
        logger.exception("ingest failed:document_id=%s",document_id)
        message = str(exc).strip() or exc.__class__.__name__
        await _set_status(document_id,DocumentStatus.FAILED,error_message=message[:500])