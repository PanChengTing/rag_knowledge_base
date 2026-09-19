from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.core.observability import build_trace_url

MessageRoleValue =Literal["user","assistant","system"]
QueryRouteValue = Literal["original","rewrite","hyde","multi_query"]
AgentActionValue = Literal["initial","proceed","rewrite_query","switch_route","refuse"]
class QueryRouteRead(BaseModel):
    route:QueryRouteValue
    query:str
    rewritten_query:str|None = None
    hyde_answer:str|None = None
    multi_querys:list[str]|None = None

class RetrievalMeta(BaseModel):
    sources:list[str] =Field(default_factory=list)
    vector_rank:int|None = None
    vector_score:float|None =None
    keyword_rank:int|None = None
    keyword_score:float|None =None
    rrf_score:float|None = None
    rerank_score:float|None =None

class AgentStep(BaseModel):
    round:int
    action:AgentActionValue
    reason:str
    route:QueryRouteValue
    query:str
    retrieved_count:int|None =None
    top_score:float|None =None
    sufficient:bool|None =None

def _parse_query_route(metadata:dict|None) ->QueryRouteRead|None:
    if not metadata:
        return None
    route = metadata.get("query_route")
    if not isinstance(route,dict):
        return None
    try:
        return QueryRouteRead.model_validate(route)
    except Exception as e:
        return None

def _parse_retrieval_meta(raw:dict|None) ->RetrievalMeta|None:
    if not isinstance(raw,dict):
        return None
    try:
        return RetrievalMeta.model_validate(raw)
    except Exception:
        return None

def _parse_agent_steps(metadata:dict|None)->list[AgentStep]|None:
    if not metadata:
        return None
    raw = metadata.get("agent_steps")
    if not isinstance(raw,list) or not raw:
        return None
    parsed:list[AgentStep]=[]
    for item in raw:
        if not isinstance(item,dict):
            return None
        try:
            parsed.append(AgentStep.model_validate(item))
        except Exception:
            return None
    return parsed

def _parse_trace_id(metadata:dict|None)->str|None:
    if not metadata:
        return None
    raw = metadata.get("trace_id")
    if not isinstance(raw,str) or not raw.strip():
        return None
    return raw

def _parse_cache_hit(metadata:dict|None)->bool:
    if not metadata:
        return False
    raw = metadata.get("cache_hit")
    return bool(raw)

class ConversationCreate(BaseModel):
    title:str =Field("新对话",min_length=1,max_length=256)

class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:UUID
    title:str
    created_at:datetime
    updated_at:datetime

class ConversationListItem(BaseModel):
    id:UUID
    title:str
    updated_at:datetime
    message_count:int

class ConversationPage(BaseModel):
    items:list[ConversationListItem]
    total:int
    page:int
    page_size:int

class VerifyResultRead(BaseModel):
    verified:bool
    reason:str|None =None

def _parse_verify_result(metadata:dict|None)->VerifyResultRead|None:
    if not metadata:
        return None
    raw = metadata.get("verify_result")
    if not isinstance(raw,dict):
        return None
    try:
        return VerifyResultRead.model_validate(raw)
    except Exception:
        return None

class CitationRead(BaseModel):
    id:UUID
    ordinal:int
    document_id:UUID|None = None
    chunk_id:UUID|None = None
    document_name:str
    page_no:int|None=None
    quote:str
    retrieval_meta:RetrievalMeta|None = None

    # 标识为类方法，因为它就是用来创建对象的，所以用类方法更好
    # 根据数据库对象创建一个给前端响应对象
    @classmethod
    def from_orm(cls, citation)->"CitationRead":
        return cls(
            id = citation.id,
            ordinal = citation.ordinal,
            document_id = citation.document_id,
            chunk_id = citation.chunk_id,
            document_name = citation.document_name,
            page_no = citation.page_no,
            quote = citation.quote,
            retrieval_meta = _parse_retrieval_meta(citation.retrieval_meta)
        )

class MessageRead(BaseModel):
    id:UUID
    role:MessageRoleValue
    content:str
    created_at:datetime
    citations:list[CitationRead] = Field(default_factory=list)
    query_route:QueryRouteRead|None = None
    agent_steps:list[AgentStep]|None =None
    verify_result:VerifyResultRead|None =None
    trace_id:str|None =None
    trace_url:str|None =None
    cache_hit:bool =False

    # 标识为类方法，因为它就是用来创建对象的，所以用类方法更好
    # 根据数据库对象创建一个给前端响应对象
    @classmethod
    def from_orm(cls, message)->"MessageRead":
        is_assistant = message.role == "assistant"
        trace_id = _parse_trace_id(message.extra_metadata) if is_assistant else None
        return cls(
            id = message.id,
            role = message.role,
            content = message.content,
            created_at = message.created_at,
            citations =[CitationRead.from_orm(c) for c in message.citations]
            if is_assistant else [],
            query_route=_parse_query_route(message.extra_metadata) 
            if is_assistant else None,
            agent_steps = _parse_agent_steps(message.extra_metadata)
            if is_assistant else None,
            verify_result = _parse_verify_result(message.extra_metadata)
            if is_assistant else None,
            cache_hit = _parse_cache_hit(message.extra_metadata)
            if is_assistant else False,
            trace_id = trace_id,
            trace_url=build_trace_url(trace_id)
        )

class ConversationDetail(BaseModel):
    conversation:ConversationRead
    message:list[MessageRead]

class ChatRequest(BaseModel):
    question:str = Field(min_length=1,max_length=2000)