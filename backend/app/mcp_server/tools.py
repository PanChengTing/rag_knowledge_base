import base64
import binascii
from typing import Literal

from mcp.server.fastmcp import FastMCP,Context
from mcp.server.fastmcp.exceptions import ToolError

from app.core.log_config import get_logger
from app.mcp_server.schemas import MCPAskAnswer
from app.mcp_server.auth import require_admin, resolve_current_user
from app.db.session import AsyncSessionLocal
from app.services.chat_service import ChatService
from app.core.exceptions import AppException
from app.services.document_service import DocumentService
from app.db.models import DocumentStatus
from app.api.shemas.documents import DocumentStatusValue
from app.services.permission_service import compute_user_permission_tag, is_admin
from app.mcp_server.schemas import MCPDocumentList,MCPDocumentStatus,MCPDocumentItem,MCPUploadResult,MCPCitation,MCPStats

logger = get_logger(__name__)

def register_tools(mcp:FastMCP)->None:
    @mcp.tool(
        name="ask_knowledge_base",
        title="知识库问答",
        description=(
            "向知识库提问并得到带引用的答案，检索按调用者的权限标签过滤"
            "命中阈值不足或答案校验未通过时返回refused=true与统一拒答文案。"
        ),
    )
    async def ask_knowledge_base(question:str,ctx:Context)->MCPAskAnswer:
        user = await resolve_current_user(ctx)
        question = question.strip()
        if not question:
            raise ToolError("question不能为空")

        async with AsyncSessionLocal() as session:
            service = ChatService(session)
            try:
                result = await service.answer_for_mcp(question,current_user=user)
            except Exception as exc:
                raise _to_tool_error(exc,default="问答处理失败") from exc

        citations =[
            MCPCitation(
                ordinal = int(c["ordinal"]),
                document_id=c["document_id"],
                document_name = c["document_name"],
                page_no= c.get("page_no"),
                section_path = c.get("section_path"),
                quote =c.get("quote","")
            )
            for c in result.citations
        ]
        return MCPAskAnswer(
            answer = result.answer,
            refused= result.refused,
            citations=citations,
            trace_id=result.trace_id
        )

    @mcp.tool(
        name="upload_document",
        title="上传文档",
        description=(
            "上传文件到知识库（仅管理员）。content_base64是文件原字节的"
            "base64编码；服务端按sha256做幂等，相同内容会复用现有文档"
            "解析与向量化由Celery异步执行，调用方可通过get_document_status轮询进度。"
        ),
    )
    async def upload_document(
        filename:str,
        content_base64:str,
        ctx:Context,
        mime_type:str|None = None,
        permission_tags:list[str]|None=None,
    )->MCPUploadResult:
        admin = await resolve_current_user(ctx)
        require_admin(admin)

        if not filename.strip():
            raise ToolError("filename不能为空")
        try:
            content = base64.b64decode(content_base64,validate=True)
        except (binascii.Error,ValueError) as exc:
            raise ToolError("content_base64不是合法的base64编码") from exc

        upload_file = _Base64UploadFile(
            filename=filename,
            content=content,
            content_type=mime_type,
        )

        async with AsyncSessionLocal() as session:
            service = DocumentService(session)
            try:
                document = await service.upload(
                    upload_file,
                    created_by=admin.id,
                    permission_tags=permission_tags
                )
            except Exception as exc:
                raise _to_tool_error(exc,default="文档上传失败") from exc

        return MCPUploadResult(
            document_id = document.id,
            name = document.name,
            status =_status_value(document.status),
            version = document.version,
            file_hash = document.file_hash
        )
    @mcp.tool(
        name = "list_documents",
        title ="列出文档",
        description = "按更新时间倒序分页列出当前用户可见的文档"
    )
    async def list_documents(
        ctx:Context,
        page:int = 1,
        page_size:int = 20,
        status:DocumentStatusValue|None = None
    )->MCPDocumentList:
        user = await resolve_current_user(ctx)
        if page<1:
            raise ToolError("page 必须>=1")
        if page_size<1 or  page_size>100:
            raise ToolError("page_size必须在1-100之间")

        async with AsyncSessionLocal() as session:
            service = DocumentService(session)
            try:
                items,total = await service.list_documents(
                    page,page_size,status=DocumentStatus(status) if status else None,
                    permission_tags=_viewer_tags(user)
                )
            except Exception as exc:
                raise _to_tool_error(exc,default="文档列表查询失败") from exc

        return MCPDocumentList(
            items=[MCPDocumentItem.model_validate(d) for d in items],
            total = total,
            page=page,
            page_size=page_size
        )

    @mcp.tool(
    name = "get_document_status",
    title ="查询文档状态",
    description = "返回文档当前状态与最近一次入库任务的进度，适合在upload_document后轮询到知道ready"
    )
    async def get_document_status(
        document_id:str,ctx:Context
    )->MCPDocumentStatus:
            user = await resolve_current_user(ctx)
            document_uuid = _parse_uuid(document_id,field="document_id")

            async with AsyncSessionLocal() as session:
                service = DocumentService(session)
                try:
                    document = await service.get(
                        document_uuid,permission_tags=_viewer_tags(user)
                    )
                    latest = await service.get_latest_task(document.id)
                except Exception as exc:
                    raise _to_tool_error(exc,default="文档状态查询失败") from exc

            return MCPDocumentStatus(
                document_id=document.id,
                name = document.name,
                status= _status_value(document.status),
                version = document.version,
                error_message = document.error_message,
                latest_task_type = _task_type_value(latest),
                latest_task_status = _task_status_value(latest),
                latest_task_progress_total = latest.progress_total if latest else None,
                latest_task_progress_done = latest.progress_done if latest else None,
                latest_task_error_message = latest.error_message if latest else None,
            )

    @mcp.tool(
    name = "get_knowledge_base_stats",
    title ="知识库概览",
    description = (
        "返回当前用户视角的文档总数/chunk总数/最近入库时间"
        "admin看全量，普通用户按照严格的权限标签后统计过滤"
    )
    )
    async def get_knowledge_base_stats(ctx:Context)->MCPStats:
        user = await resolve_current_user(ctx)
        async with AsyncSessionLocal() as session:
            service = DocumentService(session)
            try:
                stats = await service.get_stats(permission_tags=_viewer_tags(user))
            except Exception as exc:
                raise _to_tool_error(exc,default="知识库统计查询失败") from exc
        return MCPStats(
            document_count = stats.document_count,
            chunk_count = stats.chunk_count,
            last_indexed_at = stats.last_indexed_at,
        )
    
class _Base64UploadFile:
    def __init__(self,*,filename:str,content:bytes,content_type:str|None):
        self.filename = filename
        self.content_type = content_type or ""
        self._content =content

    async def read(self)->bytes:
        return self._content



#枚举转换成字符串
def _status_value(status:DocumentStatus)->DocumentStatusValue:
    return status.value

#从用户中推测出权限
def _viewer_tags(user)->list[str]|None:
    return None if is_admin(user) else compute_user_permission_tag(user)

def _to_tool_error(exc:Exception,*,default:str)->ToolError:
    if isinstance(exc,AppException):
        return ToolError(exc.message)
    logger.exception("MCP tool unexpected error")
    return ToolError(default)

def _task_type_value(task)->Literal["ingest","reindex"]|None:
    return task.task_type.value if task else None

def _task_status_value(task):
    return task.status.value if task else None

def _parse_uuid(raw:str,*,field:str):
    from uuid import UUID

    try:
        return UUID(raw)
    except (TypeError,ValueError) as exc:
        raise ToolError(f"{field}不是合法的UUID") from exc