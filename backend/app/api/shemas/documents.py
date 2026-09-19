
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#定义前后端数据交换的接口

DocumentStatusValue = Literal["uploading","parsing","indexing","ready","failed"]
IngestionTaskTypeValue = Literal["ingest","reindex"]
IngestionTaskStatusValue = Literal["pending","running","success","failed"]
class IngestionTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:UUID
    task_type:IngestionTaskTypeValue
    status:IngestionTaskStatusValue
    retry_count:int
    error_message:str|None =None
    progress_total:int
    progress_done:int
    started_at:datetime|None =None
    finish_at:datetime|None =None
    created_at:datetime|None =None


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:UUID
    name:str
    file_hash:str
    mime_type:str
    size:int
    status:DocumentStatusValue
    error_message:str|None = None
    permission_tags:list[str] = Field(default_factory=list)
    created_by:UUID|None =None
    created_at:datetime
    updated_at:datetime
    latest_task:IngestionTaskRead|None =None
    version:int=1

class DocumentListResponse(BaseModel):
    items:list[DocumentRead]
    total:int
    page:int = Field(ge=1)
    page_size:int = Field(ge=1,le=100)

_CONTENT_EXCERPT_LIMIT = 100

class DocumentChunkRead(BaseModel):
    id:UUID
    chunk_index:int
    page_no:int|None = None
    section_path:str|None = None
    content_excerpt:str
    char_count:int
    chunk_hash:str

    # 标识为类方法，因为它就是用来创建对象的，所以用类方法更好
    # 根据数据库对象创建一个给前端响应对象
    @classmethod
    def from_orm_chunk(cls, chunk)->"DocumentChunkRead":
        content = chunk.content or ""
        excerpt = content[:_CONTENT_EXCERPT_LIMIT]
        if len(content) > _CONTENT_EXCERPT_LIMIT:
            excerpt+= "..."
        return cls(
            id = chunk.id,
            chunk_index = chunk.chunk_index,
            page_no = chunk.page_no,
            section_path = chunk.section_path,
            content_excerpt = excerpt,
            char_count = len(content),
            chunk_hash = chunk.chunk_hash,
        )

class DocumentChunkStats(BaseModel):
    total:int
    avg_length:int
    min_length:int
    max_length:int

class DocumentChunkListResponse(BaseModel):
    items:list[DocumentChunkRead]
    total:int
    page:int = Field(ge=1)
    page_size:int = Field(ge=1,le=100)
    stats:DocumentChunkStats|None = None

class DocumentChunkDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:UUID
    document_id:UUID
    chunk_index:int
    content:str
    page_no:int|None =None
    section_path:str|None = None
    char_count:int
    chunk_hash:str
    created_at:datetime

    @classmethod
    def from_orm_chunk(cls, chunk)->"DocumentChunkDetail":
        return cls(
            id = chunk.id,
            document_id  = chunk.document_id,
            chunk_index =chunk.chunk_index,
            page_no = chunk.page_no,
            section_path = chunk.section_path,
            content = chunk.content,
            char_count = len(chunk.content or ""),
            chunk_hash = chunk.chunk_hash,
            created_at = chunk.created_at,
        )

class DocumentPermissionTagUpdate(BaseModel):
    permission_tags:list[str] = Field(default_factory=list)
