import asyncio
from dataclasses import dataclass
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.metrics import(
    faithfulness,
    answer_relevancy,
    context_recall,
    context_precision
)
from app.core.log_config import get_logger
from app.llm.models import get_chat_model, get_eval_model
from app.ingestion.embedder import get_embeddings


logger = get_logger(__name__)

@dataclass(frozen=True)
class RagasMetrics:
    faithfulness:float|None
    answer_relevancy:float|None
    context_precision:float|None
    context_recall:float|None

@dataclass(frozen=True)
class RagasSample:
    question:str
    answer:str
    retrieved_contexts:list[str]
    reference_answer:str

_METRICS = [faithfulness,answer_relevancy,context_precision,context_recall]

#批量计算四个指标，只需要问题、答案、参考文档、参考答案四个内容
async def evaluate_batch(samples:list[RagasSample])->list[RagasMetrics]:
    if not samples:
        return []

    dataset = EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=s.question,
                response=s.answer or "",
                retrieved_contexts=s.retrieved_contexts or [""],
                reference = s.reference_answer or ""
            )
            for s in samples
        ]
    )

    try:
        result = await asyncio.to_thread(
            evaluate,
            dataset=dataset,
            metrics=_METRICS,
            llm=get_eval_model(),
            embeddings=get_embeddings(),
            raise_exceptions=True,
            show_progress=False
        )
        logger.info("RAGAS result: %s", result)
    except Exception:
        logger.exception("RAGAS evaluate整批失败，返回None占位")
        return [_empty_metrics() for _ in samples]
    return _extract_metrics(result,expected=len(samples))

#把ragas的结果转换成自定义的数据结构
def _extract_metrics(result,expected:int)->list[RagasMetrics]:
    rows = getattr(result,"scores",None) or []
    if len(rows)!=expected:
        logger.warning(
            "RAGAS返回行数%d 与样本数%d 不一致，按可用值对齐0",len(rows),expected
        )
    metrics:list[RagasMetrics] =[]
    for i in range(expected):
        row = rows[i] if i<len(rows) else{}
        metrics.append(
            RagasMetrics(
                faithfulness=_pick(row,"faithfulness"),
                answer_relevancy=_pick(row,"answer_relevancy"),
                context_precision=_pick(row,"context_precision"),
                context_recall=_pick(row,"context_recall")
            )
        )
    return metrics

def _pick(row:dict,key:str)->float|None:
    value = row.get(key)
    if value is None:
        return None
    try:
        as_float =float(value)
    except(TypeError,ValueError):
        return None
    if as_float != as_float: #NaN
        return None
    return as_float

def _empty_metrics()->RagasMetrics:
    return RagasMetrics(
        faithfulness=None,answer_relevancy=None,
        context_precision=None,context_recall=None,
    )