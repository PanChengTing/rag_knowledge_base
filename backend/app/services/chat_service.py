from collections.abc import AsyncIterator
from uuid import UUID

from langsmith import traceable
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.log_config import get_logger
from app.retrieval.vector_retriever import RetrievedChunk
from app.db.repositories.conversation_repo import ConversationRepository
from app.db.repositories.citation_repo import AnswerCitationRepository
from app.core.exceptions import NotFoundError
from app.db.models import AnswerCitation, Conversation, Message
from app.db.session import AsyncSessionLocal
from app.workflows.rag_state import RAGState
from app.workflows.nodes import load_context
from app.workflows.nodes.normalize_query import normalize_query
from app.workflows.nodes.retrieve import retrieve
from app.workflows.nodes.generate import stream_generate
from app.workflows.nodes import route_query
from app.workflows.graph import get_rag_graph
from app.llm.answer_verifier import VerifyResult
from app.core.config import settings
from app.llm.answer_verifier import get_answer_verifier
from app.llm.prompts import REFUSAL_ANSWER
from app.core.observability import get_current_trace_id,build_trace_url


logger = get_logger(__name__)
#传入查找到的文档，将其转换成字典 ordinal从哪里来的鸭？迭代器传过来的
def _serialize_citation(chunk:RetrievedChunk,ordinal:int)->dict:
    return{
        "ordinal":ordinal,
        "chunk_id":str(chunk.chunk_id),
        "document_id":str(chunk.document_id),
        "document_name":chunk.document_name,
        "page_no":chunk.page_no,
        "section_path":chunk.section_path,
        "score":round(chunk.score,4),
        "quote":chunk.content,
        "retriecal_meta":_build_retrieval_meta(chunk),
    }
def _build_query_route_payload(state:RAGState)->dict:
    return {
        "route":state.get("route","original"),
        "query":state.get("query",""),
        "rewritten_query":state.get("rewritten_query"),
        "hyde_answer":state.get("hyde_answer"),
        "multi_querys":state.get("multi_querys"),
    }
def _build_retrieval_meta(chunk:RetrievedChunk)->dict:
    return{
        "sources":list(chunk.sources),
        "vector_rank":chunk.vector_rank,
        "vector_score":(
            round(chunk.vector_score,4) if chunk.vector_score is not None else None
        ),
        "keyword_rank":chunk.keyword_rank,
        "keyword_score":(
            round(chunk.keyword_score,4) if chunk.keyword_score is not None else None
        ),
        "rrf_score":(
            round(chunk.rrf_score,6) if chunk.rrf_score is not None else None
        ),
        "rerank_score":(
            round(chunk.rerank_score,6) if chunk.rerank_score is not None else None
        ),
    }

def _build_verify_payload(
    result:VerifyResult,*,replacement_answer:str|None     
)->dict:
    """
    replacement_answer 仅在veriried=False时携带，前端按它整段替换流式出来的答案
    """
    payload:dict ={
        "verified":result.verified,
        "reason":result.reason or None
    }
    if not result.verified and replacement_answer is not None:
        payload["replacement_answer"] =replacement_answer
    return payload

def _serialize_agent_steps(state)->list[dict]:
    return [dict(step) for step in state.get("agent_steps",[])]

class ChatService:
    def __init__(self,session:AsyncSession)->None:
        self.session = session

    async def create_conversation(self,title:str="新对话")->Conversation:
        repo = ConversationRepository(self.session)
        conversation=await repo.create(title=title)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_conversation(self,conversation_id:UUID)->Conversation:
        repo = ConversationRepository(self.session)
        conversation= await repo.get(conversation_id=conversation_id)
        if conversation is None:
            raise NotFoundError("会话不存在")
        return conversation

    async def list_messages(
            self,conversation_id:UUID
    )->tuple[Conversation,list[Message]]:
        repo = ConversationRepository(self.session)
        conversation = await self.get_conversation(conversation_id)
        messages = await repo.list_message(conversation_id)
        return conversation,messages

    async def list_conversations(
        self,page:int,page_size:int
    )->tuple[list[Conversation,int],int]:
        repo = ConversationRepository(self.session)
        return await repo.list_page(page=page,page_size=page_size)

    async def delete_conversation(
        self,conversation_id:UUID
    )->None:
        repo =ConversationRepository(self.session)
        deleted = await repo.delete(conversation_id)
        if not deleted:
            raise NotFoundError("会话不存在")
        await self.session.commit()

    async def _persist_user_message(
            self,state:RAGState,session:AsyncSession
    )->None:
        """ 流式传输开始时，先把user的消息落库
        在load_context之后调用，保证历史消息中不包含这一条
        """
        repo = ConversationRepository(session)
        #是新对话的话自动改名字
        if await repo.count_messages(state["conversation_id"]) == 0:
            await repo.update_title_if_default(
                state["conversation_id"],state["question"]
            )

        user_msg = ConversationRepository.make_user_message(
            state["conversation_id"],content=state["question"]
        )
        await repo.add_messages([user_msg])
        await session.commit()
        #更新用户会话ID
        state["user_message_id"] = user_msg.id

    async def _persist_assistant_message(
            self,state:RAGState,session:AsyncSession,*,verify_result:VerifyResult|None
    )->None:
        """在流式响应结束后，将生成完毕的完整message存到数据库
        包括检索到的完整引用文档
        """
        logger.warning("persist_assistant_message %d",len(_serialize_agent_steps(state)))
        conv_repo = ConversationRepository(session)
        citation_repo = AnswerCitationRepository(session)
        extra_meta:dict={"refused":bool(state.get("refused")),
                            "query_route":_build_query_route_payload(state),
                            "agent_steps":_serialize_agent_steps(state),
                            #落库，保证页面刷新后前端仍然可以展示
                            "trace_id":state.get("trace_id")}
        if verify_result is not None:
            extra_meta["verify_result"] = _build_verify_payload(
                verify_result,replacement_answer=None
            )
        assistant_msg = ConversationRepository.make_assistant_message(
            state["conversation_id"],
            content=state["answer"],
            extra_metadata=extra_meta
        )
        
        #flush后就有主键ID了
        await conv_repo.add_messages([assistant_msg])

        if not state.get("refused"):
            citations = [
                AnswerCitation(
                    message_id=assistant_msg.id,
                    ordinal=ordinal,
                    document_id = chunk.document_id,
                    chunk_id = chunk.chunk_id,
                    document_name = chunk.document_name,
                    page_no = chunk.page_no,
                    quote=chunk.content,
                    retrieval_meta = _build_retrieval_meta(chunk),
                )
                for ordinal,chunk in enumerate(
                    state.get("retrieved_chunks",[]),start=1
                )
            ]
            await citation_repo.bulk_add(citations)
        await session.commit()
        state["assistant_message_id"] = assistant_msg.id


    @traceable(name="ChatService.stream_answer",run_type="chain")
    async def stream_answer(
            self,conversation_id:UUID,question:str
    )->AsyncIterator[dict]:
        #事件协议 message_start->query_route->agent_steps->
        # citations->token...->[verify_result]->message_end
        #任何阶段出错都会yield error提前结束
        await self.get_conversation(conversation_id)

        #流式请求的时候单独使用session，因为流式请求的占用事件可能会比较长
        async with AsyncSessionLocal() as session:
            try:
                trace_id =get_current_trace_id()
                state:RAGState={
                    "conversation_id":conversation_id,
                    "question":question,
                    "trace_id":trace_id,
                }

                #1、加载上下文
                state.update(await load_context(state,session))
                final_state = await get_rag_graph().ainvoke(state)
                state.update(final_state)

                #2、user消息落库
                await self._persist_user_message(state,session)

                #用户的第一条消息已经存入数据库，将messageID返回，并且发送message_start开始事件
                yield{
                    "event":"message_start",
                    "data":{"user_message_id":str(state["user_message_id"]),
                            "trace_url":build_trace_url(trace_id)}
                }
                logger.warning("query_route:")
                #告诉用户走了哪条优化路径
                yield{
                    "event":"query_route",
                    "data":_build_query_route_payload(state)
                }
                logger.warning("agent_steps:")
                yield{
                    "event":"agent_steps",
                    "data":{"steps":_serialize_agent_steps(state)}
                }
                logger.warning("agent_steps end:")
                #防止agent循环中的某一轮的候选污染了数据
                citations_payload =([] if state.get("refused")
                else [
                    _serialize_citation(c,ordinal=i)
                    for i,c in enumerate(state.get("retrieved_chunks",[]),start=1)
                ])
                logger.warning("citations:")
                yield{
                    "event":"citations",
                    "data":{"citations":citations_payload}
                }

                #生成答案，拒绝回答，就不问LLM了
                verify_result:VerifyResult|None = None
                if state.get("refused"):
                    yield{
                        "event":"token",
                        "data":{"delta":state["answer"]},
                    }
                else:
                    answer_parts:list[str]=[]
                    async for delta in stream_generate(state):
                        answer_parts.append(delta)
                        yield{"event":"token","data":{"delta":delta}}
                    state["answer"]="".join(answer_parts)

                #对答案进行校验
                if settings.verify_answer_enabled:
                    verify_result = await get_answer_verifier().verify(
                        question=state["query"],
                        answer=state["answer"],
                        chunks= list(state.get("retrieved_chunks",[]))
                    )
                    replacement = (
                        REFUSAL_ANSWER if not verify_result.verified else None
                    )
                    if not verify_result.verified:
                        state["answer"]=REFUSAL_ANSWER
                        state["refused"]=True
                    yield{
                        "event":"verify_result",
                        "data":_build_verify_payload(
                            verify_result,replacement_answer=replacement
                        )
                    }

                #生成完毕，将完整答案和citations同时落库
                await self._persist_assistant_message(state,session,verify_result=verify_result)
                #告诉前端本次问答已经结束了
                yield {
                    "event":"message_end",
                    "data":{
                        "message_id":str(state["assistant_message_id"]),
                        "refused":bool(state.get("refused"))
                        }
                }
            except Exception as exc:
                logger.exception("chat stream failed:conversation_id=%s",conversation_id)
                #回滚失败的事务，用户问题可能已经独立commit，答案和引用时一起commit的，他们可以一起回滚
                await session.rollback()
                yield {
                    "event":"error",
                    "data":{
                        "code":"chat_stream_failed",
                        "message":str(exc).strip() or "问答处理失败"
                        }
                }