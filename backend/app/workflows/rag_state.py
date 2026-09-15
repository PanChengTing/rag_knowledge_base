
from typing import Literal, TypedDict
from uuid import UUID

from app.db.models import Message
from app.retrieval.vector_retriever import RetrievedChunk
#三种优化查询的方法
QueryRoute = Literal["original", "rewrite", "hyde", "multi_query"]

#total false表示每个字段都是可选的
class RAGState(TypedDict,total=False):
    #输入
    conversation_id:UUID
    question:str

    # load_context产出，从数据库中取
    chat_history:list[Message]

    #normalize_query 产出
    query:str

    #查询优化
    route:QueryRoute
    rewritten_query:str|None
    hyde_answer:str|None
    multi_querys:list[str]|None

    # retrieve产出
    retrieved_chunks:list[RetrievedChunk]
    refused:bool
    #agent决策和观察字段
    agent_steps:list[dict]|None
    retrieval_round:int|None
    #判断是否满足回答的质量
    context_sufficient:bool|None
    context_is_enough:bool

    #输出
    answer:str

    #chat_service
    user_message_id:UUID
    assistant_message_id:UUID
    trace_id:str|None
