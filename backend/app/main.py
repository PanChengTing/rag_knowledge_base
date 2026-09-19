from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.core.log_config import configure_logging, get_logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import health,documents,chat,evaluations
from app.core.config import settings
from app.api.error_handlers import register_error_handler
from app.core.observability import configure_observability
from app.db.seed import seed_default_admin
from app.api.routes import auth, roles, users
from app.mcp_server import knowledge_mcp

@asynccontextmanager
async def lifespan(app:FastAPI)->AsyncIterator[None]:
    logger = get_logger(__name__)
    #应用启动前配置，yield是应用关闭后的配置
    if not settings.jwt_secret:
        logger.error("JWT_SECRET未配置，登录功能将不可用")
    try:
        await seed_default_admin()
    except Exception:
        logger.exception("种子初始化失败！后续可以重新启动重试")
    async with knowledge_mcp.session_manager.run():
        yield

def create_app()->FastAPI:
    configure_logging()
    logger = get_logger(__name__)
    configure_observability()
    app = FastAPI(title = settings.app_name,lifespan=lifespan)
    #添加中间件，让本机的前端接口可以访问本机的后端接口，用中间件可以保证每个请求都经过中间件的处理
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handler(app)
    #给health中的所有路由加上API前缀
    app.include_router(health.router,prefix="/api")
    app.include_router(documents.router,prefix="/api")
    app.include_router(chat.router,prefix="/api")
    app.include_router(evaluations.router,prefix="/api")
    app.include_router(auth.router,prefix="/api")
    app.include_router(users.router,prefix="/api")
    app.include_router(roles.router,prefix="/api")


    app.mount("/mcp",knowledge_mcp.streamable_http_app(),name="mcp")
    logger.info("app initialized:%s",settings.app_name)
    return app

app = create_app()
