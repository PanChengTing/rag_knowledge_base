
from app.workflows.rag_state import RAGState
from app.llm.agent_planner import get_agent_planner
from app.llm.query_rewriter import get_query_rewriter
from app.core.config import settings
from app.llm.prompts import REFUSAL_ANSWER
from app.core.log_config import get_logger

logger = get_logger(__name__)
#规划下一步的计划
#更新STATE的字段，方便下一步执行，如果DESITION是refuse,则直接拒绝
async def plan_retrieval(state:RAGState)->RAGState:
    steps = list(state.get("agent_steps",[]))
    current_route = state.get("route","original")
    current_query = state.get("query" or state["question"])
    for step in steps:
        logger.info("plan_retrieval :%s",step)
    #这是第一轮的route
    if not steps:
        steps.append(
            {
                "round":1,
                "action":"initial",
                "reason":"首轮检索沿用route_query决策",
                #应该是优化后的query
                "route":current_route,
                "query":current_query,
            }
        )
        return {"agent_steps":steps}

    decision = await get_agent_planner().plan(
        question = state["query"],
        current_query=current_query,
        current_route=current_route,
        previous_steps = steps,
    )

    update:RAGState ={}
    new_route = current_route
    new_query = current_query

    if decision.action == "rewrite_query" and decision.new_query:
        #清空multi_query,防止retrieve出错
        new_query =decision.new_query
        new_route="original"
        update["query"] = new_query
        update["route"] = new_route
        update["rewritten_query"]=None
        update["hyde_answer"] = None
        update["multi_querys"] =None
    elif decision.action == "switch_route" and decision.new_route:
        rewriter = get_query_rewriter()
        result = await rewriter.apply_route(
            question=state["query"],
            route=decision.new_route,
            multi_query_count=settings.multi_query_count,
        )
        new_route = result.route
        new_query = result.query
        update["query"] = new_query
        update["route"] = new_route
        update["rewritten_query"]=result.rewritten_query
        update["hyde_answer"] = result.hyde_answer
        update["multi_querys"] =result.multi_querys

    steps.append(
        {
            "round":len(steps)+1,
            "action":decision.action,
            "reason":decision.reason,
            "route":new_route,
            "query":new_query,
        }
    )
    for step in steps:
        logger.info("plan_retrieval :%s",step)
    update["agent_steps"]=steps

    return update