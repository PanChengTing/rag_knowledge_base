
import json
from uuid import UUID
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, Form, Header, Query, Response, UploadFile

from app.api.deps import CurrentAdmin, CurrentUser, DbSession
from app.api.shemas.documents import DocumentChunkDetail, DocumentChunkListResponse, DocumentChunkRead, DocumentChunkStats, DocumentPermissionTagUpdate, DocumentRead, DocumentStatusValue
from app.services.document_service import DocumentService
from app.db.models import DocumentStatus
from app.api.shemas.documents import DocumentListResponse
from app.services.permission_service import compute_user_permission_tag, is_admin


router  = APIRouter(prefix="/documents",tags=["documents"])

def _viewer_tags(user)->list[str]|None:
        return None if is_admin(user) else compute_user_permission_tag(user)

@router.post("",response_model=DocumentRead,status_code=201,operation_id="upload_document")
async def upload_document(
        admin:CurrentAdmin,
        session:DbSession,
        background_tasks:BackgroundTasks,
        file:UploadFile= File(...,description="待上传文档（PDF/DOCX/MARKDOWN/HTML）",),
        permission_tags:str|None =Form(
                default=None,
                description = 'JSON数组字符串，例如["public","hr"]'
        )
)->DocumentRead:
    tags:list[str]=[]
    if permission_tags:
        try:
                parsed = json.loads(permission_tags)
        except json.JSONDecodeError:
                parsed = [permission_tags]
        if isinstance(parsed,list):
                tags = [str(t) for t in parsed]
    service = DocumentService(session)
    document = await service.upload(file,background_tasks,
                                    created_by=admin.id,
                                    permission_tags=tags)
    #自动将数据库模型转换为这个类
    return DocumentRead.model_validate(document)

@router.get("",response_model=DocumentListResponse,operation_id="listDocuments")
async def list_documents(
        user:CurrentUser,
        session:DbSession,
        page:int = Query(1,ge =1),
        page_size:int = Query(20,ge =1,le=100),
        status:DocumentStatusValue|None = Query(None,description="按文档状态筛选"))->DocumentListResponse:
            service = DocumentService(session)
            items,total = await service.list_documents(
                page,
                page_size,
                status =DocumentStatus(status) if status else None,
                permission_tags=_viewer_tags(user)
            )
            return DocumentListResponse(
                    items=[DocumentRead.model_validate(d) for d in items],
                    total=total,
                    page = page,
                    page_size=page_size,
            )

@router.get("/{document_id}",response_model=DocumentRead,operation_id="getDocument")
async def get_document(document_id:UUID,session:DbSession,user:CurrentUser)->DocumentRead:
        service = DocumentService(session)
        document = await service.get(document_id,permission_tags=_viewer_tags(user))
        return DocumentRead.model_validate(document)

@router.delete("/{document_id}",status_code=204,operation_id="deleteDocument")
async def delete_document(_:CurrentAdmin,document_id:UUID,session:DbSession,admin:CurrentAdmin)->Response:
        service = DocumentService(session)
        await service.delete(document_id)
        return Response(status_code=204)

@router.post("/{document_id}",response_model=DocumentRead,operation_id="retryDocument")
async def retry_document(_:CurrentAdmin,document_id:UUID,session:DbSession,background_tasks:BackgroundTasks,)->DocumentRead:
        service = DocumentService(session)
        document = await service.retry(document_id,background_tasks)
        return DocumentRead.model_validate(document)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/{document_id}/file",operation_id="downloadDocument")
async def download_document(
    document_id:UUID,
    session:DbSession,
    token:str|None = Query(None,description="Bearer token"),
    authorization:str|None = Header(None,alias="Authorization"),
    #ge greater than or equal le less than or equal
    download:int = Query(0,ge=0,le=1,description="1=强制下载 0=尝试内联预览"),    
)->Response:
    from app.api.deps import get_current_user
    effective_auth = authorization or(f"Bearer {token}" if token else None)
    user = await get_current_user(session,effective_auth)
    service = DocumentService(session)
    document = await service.get(document_id,permission_tags=_viewer_tags(user))
    content = await service.file_service.download(document.cos_object_key)

    #用户要求下载或者文件类型是DOCX，强制下载
    force_attachment = download==1 or document.mime_type == _DOCX_MIME
    disposition = "attachment" if force_attachment else "inline"
    #将中文文件名进行安全编码
    filename_quoted = quote(document.name,safe="")

    return Response(
           content=content,
           media_type=document.mime_type,
           #inline和attachment是发给浏览器的，是规定的标准取值，inline是在浏览器中显示，attachment作为附件下载
           headers={
                  "Content-Disposition":(
                         f"{disposition};filename*=UTF-8''{filename_quoted}"
                  ),
           },
    )

@router.get("/{document_id}/chunks",
            response_model=DocumentChunkListResponse,
            operation_id="listDocumentsChunks")
async def list_documents_chunks(
        user:CurrentUser,
        document_id:UUID,
        session:DbSession,
        page:int = Query(1,ge =1),
        page_size:int = Query(20,ge =1,le=100))->DocumentChunkListResponse:
            service = DocumentService(session)
            items,total,stats = await service.list_chunks(
                document_id,
                page,
                page_size,
                permission_tags=_viewer_tags(user)
            )
            return DocumentChunkListResponse(
                    items=[DocumentChunkRead.from_orm_chunk(c) for c in items],
                    total=total,
                    page = page,
                    page_size=page_size,
                    stats=DocumentChunkStats(
                        total=stats.total,
                        avg_length=stats.avg_length,
                        max_length=stats.max_length,
                        min_length=stats.min_length,
                    )
                    if stats is not None else None,
            )

@router.get(
            "/{document_id}/chunks/{chunk_id}",
            response_model=DocumentChunkDetail,
            operation_id="getDocumentsChunk",
)
async def get_document_chunk(
        user:CurrentUser,
        document_id:UUID,
        session:DbSession,
        chunk_id:UUID,
)->DocumentChunkDetail:
        service = DocumentService(session)
        chunk = await service.get_chunk(document_id,chunk_id,permission_tags=_viewer_tags(user))
        return DocumentChunkDetail.from_orm_chunk(chunk)

@router.patch(
        "/{document_id}/permission-tags",
        response_model=DocumentRead,
        operation_id="updateDocumentPermissionTags",
)
async def update_permission_tags(
        _:CurrentAdmin,
         document_id:UUID,
        session:DbSession, 
        payload:DocumentPermissionTagUpdate,
)->DocumentRead:
        service = DocumentService(session) 
        document = await service.update_permission_tags(
                document_id,payload.permission_tags
        )
        return DocumentRead.model_validate(document)