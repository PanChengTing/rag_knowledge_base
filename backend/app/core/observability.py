"""
设计意图：
-把langsmith的具体SDK调用收敛到一个文件，让业务代码只看到“@traeable”装饰器
和“get_current_trace_id()”两个稳定符号
-langsmithSDK 内部从环境变量中读取API KEY，因此需要将settings中的变量同步成
langsmith官方环境变量
"""
from app.core.log_config import get_logger
from app.core.config import settings
import os

logger = get_logger(__name__)

#将所有配置同步到环境变量
def configure_observability()->None:
    if settings.observablility_enabled:
        os.environ["LANGSMITH_TRACING"] ="true"
        os.environ["LANGSMITH_API_KEY"]=settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"]=settings.langsmith_project
        os.environ["LANGSMITH_ENDPOINT"]=settings.langsmith_endpoint
        logger.info("LangSmith tracing enabled:project=%s endpoint=%s",
                    settings.langsmith_project,
                    settings.langsmith_endpoint)
    else:
        os.environ["LANGSMITH_TRACING"] ="false"
        logger.info("LangSmith tracing disabled(no LANGSMITH_API_KEY or switch off)")

#返回正在执行的traceable的节点对象的trace_id
def get_current_trace_id()->str|None:
    if not settings.observablility_enabled:
        return None
    try:
        from langsmith.run_helpers import get_current_run_tree
        run = get_current_run_tree()
        if run is None:
            return None
        return str(run.trace_id)
    except Exception:
        logger.warning("get_current_trace_id异常",exc_info=True)
        return None

def build_trace_url(trace_id:str|None)->str|None:
    if not trace_id or not settings.langsmith_run_url_prefix:
        return None
    return f"{settings.langsmith_run_url_prefix.rstrip('/')}/r/{trace_id}"