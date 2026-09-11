
from collections.abc import AsyncIterable
from uuid import UUID

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.shemas.chat import ConversationCreate
from app.api.deps import DbSession
from app.api.shemas.chat import ConversationRead
from app.services.chat_service import ChatService
from app.api.shemas.chat import ConversationDetail,MessageRead,ChatRequest

router = APIRouter(prefix="/conversations",tags=["chat"])

#创建新的对话
@router.post(
        "",
        response_model=ConversationRead,
        status_code=201,
        operation_id="createConversation"
)
async def create_conversation(
        payload:ConversationCreate,
        session:DbSession,
)->ConversationRead:
    service = ChatService(session)
    conversation = await service.create_conversation(title=payload.title)
    return ConversationRead.model_validate(conversation)


@router.get(
        "/{conversation_id}",
        operation_id="getConversation",
        response_model=ConversationDetail
)
async def get_conversation(
        conversation_id:UUID,
        session:DbSession
)->ConversationDetail:
    service = ChatService(session)
    conversation,messages = await service.list_messages(conversation_id)
    return ConversationDetail(
        conversation=ConversationRead.model_validate(conversation),
        message = [MessageRead.from_orm(m) for m in messages]
    )

@router.post(
    "/{conversation_id}/chat",
    operation_id="streamChat",
    response_class=EventSourceResponse,   
)
async def stream_chat(
    conversation_id:UUID,
    session:DbSession,
    payload:ChatRequest,
)->AsyncIterable[ServerSentEvent]:
    service = ChatService(session)
    async for sse_event in service.stream_answer(conversation_id,payload.question):
        yield ServerSentEvent(
            data = sse_event["data"],
            event=sse_event["event"]
        )