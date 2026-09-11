from collections.abc import AsyncIterator

from app.llm.models import get_chat_model
from app.llm.prompts import build_answer_messages
from app.workflows.rag_state import RAGState
#流式生成答案
async def stream_generate(state:RAGState)->AsyncIterator[str]:
    message = build_answer_messages(
        question=state["question"],
        chunks=state["retrieved_chunks"],
        history=state.get("chat_history",[])
    )
    async for chunk in get_chat_model().astream(message):
        text = chunk.content
        if not text:
            continue
        # langchain给出的答案有str和list两种，一般都是走str
        if isinstance(text,str):
            yield text
        else:
            yield "".join(part.get("text","") for part in text if isinstance(part,dict))