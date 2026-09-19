import asyncio
from uuid import UUID
from langchain_core.documents import Document as LangChainDocument

from app.core.log_config import get_logger
from app.db.models import DocumentChunk, DocumentStatus
from app.db.repositories.chunk_repo import DocumentChunkRepository
from app.db.repositories.document_repo import DocumentRepository
from app.db.session import AsyncSessionLocal
from app.ingestion import embedder
from app.storage.file_service import get_file_service
from app.ingestion import parser
from app.ingestion import splitter
from app.db.repositories.ingestion_task_repo import IngestionTaskRepository

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
                        embedding = vec,
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

async def _run_ingest(document_id:UUID,task_id:UUID)->None:
    logger.info("ingest start document_id=%s task_id=%s",document_id,task_id)
    await _mark_task(task_id,running=True)
    try:
        async with AsyncSessionLocal() as session:
            document = await DocumentRepository(session).get_by_id(document_id)
            if document is None:
                logger.warning("document not found,skip ingest:%s",document_id)
                await _mark_task_failed(task_id,"文档不存在")
                return
            object_key = document.cos_object_key
            filename = document.name

        await _set_status(document_id,DocumentStatus.PARASING)
        content = await get_file_service().download(object_key)
        parsed = await parser.parse(filename,content)

        #将文档切分成chunk
        await _set_status(document_id,DocumentStatus.INDEXING)
        chunks = splitter.split(parsed)
        if not chunks:
            raise ValueError("切分后没有任何chunk,请检查文档内容")

        await _set_task_total(task_id,len(chunks))
        embeddings = await _embed_with_progress(
            [c.page_content for c in chunks],task_id
        )
        async with AsyncSessionLocal() as session:
            chunk_repo = DocumentChunkRepository(session)
            await chunk_repo.bulk_add(
                [_make_chunk(document_id,c,vec) for c,vec in zip(chunks,embeddings,strict=True)]
            )
            await session.commit()

        await _set_status(document_id,DocumentStatus.READY,error_message=None)
        await _mark_task_success(task_id)
        logger.info("ingest done:document_id=%s chunks=%d",document_id,len(chunks))

    except Exception as exc:
        logger.exception("ingest failed:document_id=%s",document_id)
        message = str(exc).strip() or exc.__class__.__name__
        await _set_status(document_id=document_id,status=DocumentStatus.FAILED,error_message=message[:500])
        await _mark_task_failed(task_id,message)

async def _run_reindex(document_id:UUID,task_id:UUID)->None:
    logger.info("reindex start document_id=%s task_id=%s",document_id,task_id)
    await _mark_task(task_id,running=True)
    try:
        async with AsyncSessionLocal() as session:
            document = await DocumentRepository(session).get_by_id(document_id)
            if document is None:
                logger.warning("document not found,skip ingest:%s",document_id)
                await _mark_task_failed(task_id,"文档不存在")
                return
            object_key = document.cos_object_key
            filename = document.name
        await _set_status(document_id,DocumentStatus.PARASING)
        content = await get_file_service().download(object_key)
        parsed = await parser.parse(filename,content)

        #将文档切分成chunk
        await _set_status(document_id,DocumentStatus.INDEXING)
        new_chunks = splitter.split(parsed)
        if not new_chunks:
            raise ValueError("切分后没有任何chunk,请检查文档内容")
        async with AsyncSessionLocal() as session:
            old_chunks = await DocumentChunkRepository(session).list_all_by_document(
                document_id
            )
        if _has_duplicate_hash(new_chunks):
            logger.warning(
                "reindex fallback to full rebuild due to duplicate chunk hash:%s",document_id
            )
            await _run_full_rebuild(document_id,task_id,new_chunks)
        else:
            await _run_incremental(document_id,task_id,old_chunks,new_chunks)

        async with AsyncSessionLocal() as session:
            doc_repo = DocumentRepository(session)
            doc = await doc_repo.get_by_id(document_id)
            if doc is not None:
                doc.version+=1
            await session.commit()

        await _set_status(document_id,DocumentStatus.READY,error_message=None)
        await _mark_task_success(task_id)
    
    except Exception as exc:
        logger.exception("ingest failed:document_id=%s",document_id)
        message = str(exc).strip() or exc.__class__.__name__
        await _set_status(document_id=document_id,status=DocumentStatus.FAILED,error_message=message[:500])
        await _mark_task_failed(task_id,message)

async def _mark_task(task_id:UUID,*,running:bool=False)->None:
    async with AsyncSessionLocal() as session:
        repo = IngestionTaskRepository(session)
        if running:
            await repo.mark_running(task_id)
        await session.commit()

async def _mark_task_failed(task_id:UUID,error_message:str)->None:
    async with AsyncSessionLocal() as session:
        repo = IngestionTaskRepository(session)
        await repo.mark_failed(task_id,error_message)
        await session.commit()

async def _mark_task_success(task_id:UUID)->None:
    async with AsyncSessionLocal() as session:
        repo = IngestionTaskRepository(session)
        await repo.mark_success(task_id)
        await session.commit()

async def _set_task_total(task_id: UUID, total: int) -> None:
    async with AsyncSessionLocal() as session:
        repo = IngestionTaskRepository(session)
        await repo.set_progress_total(task_id, total)
        await session.commit()

async def _increment_task_progress(task_id: UUID, delta: int) -> None:
    async with AsyncSessionLocal() as session:
        repo = IngestionTaskRepository(session)
        await repo.increment_progress(task_id, delta)
        await session.commit()

def _has_duplicate_hash(chunks:list[LangChainDocument])->bool:
    seen:set[str]=set()
    for c in chunks:
        h = c.metadata["chunk_hash"]
        if h in seen:
            return True
        seen.add(h)
    return False

async def _run_incremental(
        document_id:UUID,
        task_id:UUID,
        old_chunks:list[DocumentChunk],
        new_chunks:list[LangChainDocument],
)->None:
    old_by_hash = {c.chunk_hash:c for c in old_chunks}
    new_hashes = {c.metadata["chunk_hash"] for c in new_chunks}

    to_delete_ids:list[UUID]=[
        c.id for c in old_chunks if c.chunk_hash not in new_hashes
    ]
    to_insert:list[LangChainDocument]=[]
    to_update:list[tuple[DocumentChunk,LangChainDocument]] = []
    for nc in new_chunks:
        h = nc.metadata["chunk_hash"]
        existing = old_by_hash.get(h)
        if existing is None:
            to_insert.append(nc)
        else:
            to_update.append((existing,nc))

    await _set_task_total(task_id,len(to_insert))
    new_embeddings = await _embed_with_progress(
        [c.page_content for c in to_insert],task_id
    )

    async with AsyncSessionLocal() as session:
        chunk_repo = DocumentChunkRepository(session)
        await chunk_repo.delete_by_ids(to_delete_ids)

        for old,nc in to_update:
            old.chunk_index = nc.metadata["chunk_index"]
            old.page_no = nc.metadata.get("page_no")
            old.section_path = nc.metadata.get("section_path")
            old.extra_metadata = nc.metadata

        await chunk_repo.bulk_add(
            [
                _make_chunk(document_id,c,vec)
                for c,vec in zip(to_insert,new_embeddings,strict=True)
            ]
        )
        await session.commit()

async def _run_full_rebuild(
        document_id:UUID,task_id:UUID,new_chunks:list[LangChainDocument]
)->None:
    await _set_task_total(task_id,len(new_chunks))
    embeddings = await _embed_with_progress(
        [c.page_content for c in new_chunks],task_id
    )

    async with AsyncSessionLocal() as session:
        chunk_repo = DocumentChunkRepository(session)
        await chunk_repo.delete_by_document(document_id)
        await chunk_repo.bulk_add(
            [
                _make_chunk(document_id,c,vec)
                for c,vec in zip(new_chunks,embeddings,strict=True)
            ]
        )
        await session.commit()

def _make_chunk(
    document_id:UUID,chunk:LangChainDocument,embedding:list[float]
)->DocumentChunk:
    return DocumentChunk(
        document_id = document_id,
        content = chunk.page_content,
        embedding = embedding,
        page_no=chunk.metadata.get("page_no"),
        section_path=chunk.metadata.get("section_path"),
        chunk_index = chunk.metadata["chunk_index"],
        chunk_hash = chunk.metadata["chunk_hash"],
        extra_metadata = chunk.metadata
    )
    
#分批次对文档切片进行向量化，并且把加到task的进度上
async def _embed_with_progress(
        texts:list[str],task_id:UUID
)->list[list[float]]:
    from app.core.config import settings

    if not texts:
        return []
    embeddings_client = embedder.get_embeddings()
    batch_size = max(1,settings.embedding_batch_size)
    results:list[list[float]] =[]
    for start in range(0,len(texts),batch_size):
        batch = texts[start:start+batch_size]
        vectors = await embeddings_client.aembed_documents(batch)
        results.extend(vectors)
        await _increment_task_progress(task_id,len(batch))
    return results

def run_ingest_sync(document_id:UUID,task_id:UUID)->None:
    asyncio.run(_run_ingest(document_id,task_id))

def run_reindex_sync(document_id:UUID,task_id:UUID)->None:
    asyncio.run(_run_reindex(document_id,task_id))