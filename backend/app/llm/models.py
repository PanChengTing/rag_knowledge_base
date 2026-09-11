from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.exceptions import ConfigurationError

_chat_model:BaseChatModel|None = None

def get_chat_model()->BaseChatModel:
    global _chat_model
    if _chat_model is not None:
        return _chat_model
    if not settings.chat_api_key:
        raise ConfigurationError("CHAT API key未配置，请在.env文件中配置CHAT_API_KEY")

    _chat_model = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.chat_api_key,
        base_url=settings.chat_base_url,
        temperature=0,
        streaming=True,
    )
    return _chat_model

