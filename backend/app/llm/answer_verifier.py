
from dataclasses import dataclass
import json

from app.retrieval.vector_retriever import RetrievedChunk
from app.llm.prompts import build_verify_answer_messages, format_context
from app.llm.models import get_chat_model
from app.core.log_config import get_logger

logger = get_logger(__name__)
@dataclass(frozen=True)
class VerifyResult:
    verified:bool
    reason:str

def _extract_text(text:str|list[str|dict])->str:
    if isinstance(text, str):
        return text
    elif isinstance(text, list):
        return " ".join(part.get("text","") for part in text if isinstance(part, dict))
    else:
        raise ValueError(f"Unexpected type for text: {type(text)}")
    
class AnswerVerifier:
    async def verify(
            self,
            question:str,
            answer:str,
            chunks:list[RetrievedChunk]
    )->VerifyResult:
        if not chunks or not answer.strip():
            return VerifyResult(verified=True,reason="")
        messages = build_verify_answer_messages(question=question,answer=answer,chunks_text=format_context(chunks))
        try:
            response = await get_chat_model().ainvoke(messages)
            raw= _extract_text(response.content).strip()
            return _parse_result(raw)
        except Exception:
            logger.exception("answer verifier 调用失败，降级verified=True:question:%r",question)
            return VerifyResult(verified=True,reason="verifier_exception")
        return VerifyResult(verified=True,reason="verifier_exception")

#对大模型的回答进行转换成一个对象
def _parse_result(raw:str)->VerifyResult:
    text = raw.strip()
    #处理模型包一层 ```json ...```的情况
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("answer verifier JSON 解析失败，降级verified=True:question:%r",raw)
        return VerifyResult(verified=True,reason="verifier_parse_exception")

    if not isinstance(data,dict):
        return VerifyResult(verified=True,reason="verifier_parse_exception")
    verified_raw = data.get("verified")
    if not isinstance(verified_raw,bool):
        logger.warning("answer verifier 返回verified字段非布尔，降级verified=True:question:%r",raw)
        return VerifyResult(verified=True,reason="verifier_invalid_exception")
    reason = str(data.get("reason")or"").strip()
    return VerifyResult(verified=verified_raw,reason=reason)

    
_verifier:AnswerVerifier|None =None
def get_answer_verifier()->AnswerVerifier:
    global _verifier
    if _verifier is None:
        _verifier =AnswerVerifier()
    return _verifier
