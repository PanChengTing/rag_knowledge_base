from dataclasses import dataclass
import json
from typing import Literal, get_args

from app.core.log_config import get_logger
from app.workflows.rag_state import QueryRoute
from app.llm.prompts import build_agent_plan_messages
from app.llm.models import get_chat_model


logger = get_logger(__name__)

AgentAction = Literal["proceed","rewrite_query","switch_route","refuse"]
_VALID_ACTIONS:tuple[str,...] = get_args(AgentAction)
_VALID_ROUTES:tuple[str,...] = get_args(QueryRoute)

@dataclass(frozen = True)
class AgentDecision:
    action:AgentAction
    reason:str
    new_query:str|None =None
    new_route:str|None = None

class AgentPlanner:
    async def plan(
        self,
        question:str,
        current_route:QueryRoute,
        current_query:str,
        previous_steps:list[dict] ,
    )->AgentDecision:
        history = _format_history(previous_steps)
        messages = build_agent_plan_messages(
            question=question,
            current_query=current_query,
            current_route=current_route,
            history=history,
        )
        try:
            response = await get_chat_model().ainvoke(messages)
            raw = _extract_text(response.content).strip()
            return _parse_decision(raw)
        except Exception:
            logger.exception("agent planner 调用失败，降级proceed:question=%r",question)
            return AgentDecision(action="proceed",reason="planner_exception")

_planner:AgentPlanner|None =None
def get_agent_planner()->AgentPlanner:
    global _planner
    if _planner is None:
        _planner = AgentPlanner()
    return _planner

#把历史结果合并成一个string
def _format_history(steps:list[dict])->str:
    if not steps:
        return "(无)"
    lines:list[str]=[]
    for step in steps:
        lines.append(
            f"- round{step.get('round')}:action={step.get('action')},"
            f"route={step.get('route')},query={step.get('query')!r},"
            f"retrieved_count={step.get('retrieved_count')},"
            f"top_score={step.get('top_score')},"
            f"sufficient={step.get('sufficient')}"
        )
    return "\n".join(lines)

#处理模型给出的答案，从里面提取出下一步行为，并且处理异常情况，降级为proceed
def _parse_decision(raw:str)->AgentDecision:
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
        logger.warning("agent planner JSON 解析失败，降级proceed:raw=%r",raw)
        return AgentDecision(action="proceed",reason="planner_parse_failed")

    if not isinstance(data,dict):
        return AgentDecision(action="proceed",reason="planner_parse_failed")

    action = str(data.get("action","")).strip().lower()
    if action not in _VALID_ACTIONS:
        logger.warning("agent planner 返回非法的action=%r,降级proceed",action)
        return AgentDecision(action="proceed",reason="planner_parse_failed")
    reason = str(data.get("reason","")).strip() or "(no reason)"
    new_query_raw = data.get("new_query")
    new_query = (
        str(new_query_raw).strip()
        if isinstance(new_query_raw,str) and new_query_raw.strip()
        else None
    )

    new_route_raw = data.get("new_route")
    new_route:QueryRoute|None =None
    if isinstance(new_route_raw,str) and new_route_raw.strip().lower() in _VALID_ROUTES:
        new_route = new_route_raw.strip().lower()

    if action == "rewrite_query" and not new_query:
        logger.warning("agent planner action=rewrite_query 缺少new_query,降级proceed")
        return AgentDecision(action="proceed",reason="planner_missing_query")

    if action == "switch_route" and new_route is None:
        logger.warning("agent planner action=switch_route new_route,降级proceed")
        return AgentDecision(action="proceed",reason="planner_missing_route")
    return AgentDecision(
        action=action,
        reason=reason,
        new_route=new_route,
        new_query=new_query,
    )


def _extract_text(text:str|list[str|dict])->str:
    if isinstance(text, str):
        return text
    elif isinstance(text, list):
        return " ".join(part.get("text","") for part in text if isinstance(part, dict))
    else:
        raise ValueError(f"Unexpected type for text: {type(text)}")