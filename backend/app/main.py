from app.core.log_config import configure_logging, get_logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import health,documents,chat
from app.core.config import settings
from app.api.error_handlers import register_error_handler

def create_app()->FastAPI:
    configure_logging()
    logger = get_logger(__name__)

    app = FastAPI(title = settings.app_name)
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

    logger.info("app initialized:%s",settings.app_name)
    return app

app = create_app()
