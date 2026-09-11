from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.workflows.rag_state import RAGState
from app.db.repositories.conversation_repo import ConversationRepository


async def load_context(state:RAGState,session:AsyncSession)->RAGState:
    repo = ConversationRepository(session)
    #取最近的多条消息 *2是因为user/assitant算一对
    history = await repo.recent_messages(
        state["conversation_id"],limit=settings.chat_history_window*2
    )
    return {"chat_history":history}