from dataclasses import dataclass
from typing import Literal


BadCaseCategory = Literal[
    "document_parse_failed",
    "chunk_split_bad",
    "embedding_recall_miss",
    "keyword_recall_miss",
    "rrf_fusion_error",
    "rerank_order_error",
    "context_judge_too_loose",
    "context_judge_too_strict",
    "prompt_constraint_weak",
    "generaion_off_context",
    "citation_parse_failed",
    "permission_filter_error",
    "other",
]

_LOW_SCORE_THRESHOLD = 0.5

@dataclass(frozen=True)
class BadCaseRule:
    is_bad_case:bool
    category:BadCaseCategory|None

def compute_citation_hit(
        actual_citaions:list[dict],
        expected_document_names:list[str],
        expected_keywords:list[str],
)->bool:
    #引用命中率
    #citations中的document_name出现在expected_document_names
    #任何一个citations中的quote出现在expected_keywords
    if not actual_citaions:
          return False
    actual_doc_names = {c.get("document_name","") for c in actual_citaions}
    if any(name in actual_doc_names for name in expected_document_names if name):
          return True

    if expected_keywords:
        #提取中引用中的quote?有这个字段嘛
        quote_blob ="\n".join(str(c.get("quote","")) for c in actual_citaions)
        if any(kw in quote_blob for kw in expected_keywords if kw):
            return True
    return False

def compute_refusal_correct(actual_refused:bool,should_refuse:bool)->bool:
     return actual_refused==should_refuse

def classify_bad_case(
          *,
          should_refuse:bool,
          actual_refused:bool,
          refusal_correct:bool,
          citation_hit:bool|None,
          faithfulness:float|None,
          answer_relevancy:float|None,
          context_precision:float|None,
          context_recall:float|None,
          has_error:bool,
)->BadCaseRule:
     if has_error:
          return BadCaseRule(is_bad_case=True,category="other")
     #拒答错误：该拒绝不拒绝，不该拒绝却拒绝了
     if not refusal_correct:
          if should_refuse and not actual_refused:
               return BadCaseRule(is_bad_case=True,category="context_judge_too_loose")
          return BadCaseRule(is_bad_case=True,category="context_judge_too_strict")

        #没有命中citation
     if citation_hit is False:
          return BadCaseRule(is_bad_case=True,category="embedding_recall_miss")

     #RAGAS指标顺序，先看召回，再看排序->生成忠实度->答案相关性(表达，可能忠于引用，但是表达不准确)
     if _is_low(context_recall):
          return BadCaseRule(is_bad_case=True,category="embedding_recall_miss")
     if _is_low(context_precision):
          return BadCaseRule(is_bad_case=True,category="rerank_order_error")
     if _is_low(faithfulness):
          return BadCaseRule(is_bad_case=True,category="generaion_off_context")
     if _is_low(answer_relevancy):
          return BadCaseRule(is_bad_case=True,category="prompt_constraint_weak")
     return BadCaseRule(is_bad_case=False,category=None)

def _is_low(score:float|None)->bool:
     return score is not None and score<_LOW_SCORE_THRESHOLD
     