from collections.abc import AsyncIterator
from uuid import UUID

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
        )
    }
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

    async def _persist_user_message(
            self,state:RAGState,session:AsyncSession
    )->None:
        """ 流式传输开始时，先把user的消息落库
        在load_context之后调用，保证历史消息中不包含这一条
        """
        repo = ConversationRepository(session)
        user_msg = ConversationRepository.make_user_message(
            state["conversation_id"],content=state["question"]
        )
        await repo.add_messages([user_msg])
        await session.commit()
        #更新用户会话ID
        state["user_message_id"] = user_msg.id


    async def _persist_assistant_message(
            self,state:RAGState,session:AsyncSession
    )->None:
        """在流式响应结束后，将生成完毕的完整message存到数据库
        包括检索到的完整引用文档
        """
        conv_repo = ConversationRepository(session)
        citation_repo = AnswerCitationRepository(session)
        assistant_msg = ConversationRepository.make_assistant_message(
            state["conversation_id"],
            content=state["answer"],
            extra_metadata={"refused":bool(state.get("refused")),
                            "query_route":_build_query_route_payload(state)},
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


    async def stream_answer(
            self,conversation_id:UUID,question:str
    )->AsyncIterator[dict]:
        #事件协议 message_start->citations->token...->message_end
        #任何阶段出错都会yield error提前结束
        await self.get_conversation(conversation_id)

        #流式请求的时候单独使用session，因为流式请求的占用事件可能会比较长
        async with AsyncSessionLocal() as session:
            try:
                state:RAGState={
                    "conversation_id":conversation_id,
                    "question":question
                }

                #1、加载上下文
                state.update(await load_context(state,session))
                state.update(await normalize_query(state))
                state.update(await route_query(state))

                #2、user消息落库
                await self._persist_user_message(state,session)

                #用户的第一条消息已经存入数据库，将messageID返回，并且发送message_start开始事件
                yield{
                    "event":"message_start",
                    "data":{"user_message_id":str(state["user_message_id"])}
                }

                yield{
                    "event":"query_route",
                    "data":_build_query_route_payload(state)
                }

                #查找参考资料，先把参考资料发给用户
                state.update(await retrieve(state))
                citations_payload =[
                    _serialize_citation(c,ordinal=i)
                    for i,c in enumerate(state.get("retrieved_chunks",[]),start=1)
                ]
                yield{
                    "event":"citations",
                    "data":{"citations":citations_payload}
                }

                #生成答案，拒绝回答，就不问LLM了
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

                #生成完毕，将完整答案和citations同时落库
                await self._persist_assistant_message(state,session)
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