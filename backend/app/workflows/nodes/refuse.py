from app.workflows.rag_state import RAGState
from app.llm.prompts import REFUSAL_ANSWER

async def refuse(state:RAGState)->RAGState:
    return {"refused":True,"answer":REFUSAL_ANSWER}