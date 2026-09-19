from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.shemas.documents import DocumentStatusValue, IngestionTaskStatusValue


class MCPCitation(BaseModel):
    ordinal:int = Field(description="prompt 中给LLM的片段N编号，从1开始")
    document_id:UUID
    document_name:str
    page_no:int|None=None
    section_path:str|None=None
    quote:str = Field(description="该片段在prompt里的原文")

class MCPAskAnswer(BaseModel):
    answer:str
    refused:bool = Field(description="是否触发拒答（命中阈值不足或答案校验失败）")
    citations:list[MCPCitation]=Field(default_factory=list)
    trace_id:str|None = Field(
        default=None,description="LangSmith trace_id,未启用观测时为空"
    )

class MCPUploadResult(BaseModel):
    document_id:UUID
    name:str
    status:DocumentStatusValue
    version:int
    file_hash:str = Field(
        description="sha256;文件集幂等键，相同hash复用现有文档"
    )

class MCPDocumentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:UUID
    name:str
    mime_type:str
    size:int
    status:DocumentStatusValue
    permission_tags:list[str] = Field(default_factory=list)
    created_at:datetime
    updated_at:datetime
    version:int=1

class MCPDocumentList(BaseModel):
    items:list[MCPDocumentItem]
    total:int
    page:int = Field(ge=1)
    page_size:int = Field(ge=1,le=100)

class MCPDocumentStatus(BaseModel):
    document_id:UUID
    name:str
    status:DocumentStatusValue
    version:int
    error_message:str|None =None
    latest_task_type:Literal["ingest","reindex"]|None= None
    latest_task_status:IngestionTaskStatusValue|None = None
    latest_task_progress_total:int|None =None
    latest_task_progress_done:int|None=None
    latest_task_error_message:str|None =None

class MCPStats(BaseModel):
    document_count:int
    chunk_count:int
    last_indexed_at:datetime|None=Field(
        default=None,description="最后一次进入ready状态的文档时间，库返回时返回null"
    )

