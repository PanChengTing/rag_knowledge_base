
from app.core.log_config import get_logger
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from app.core.exceptions import AppException

loggger = get_logger(__name__)

#_表示这个变量暂时不使用
async def _app_exception_handler(_:Request,exc:AppException) ->JSONResponse:
    return JSONResponse(
        status_code = exc.http_status,
        content={"code":exc.code,"message":exc.message}
    )

async def _unhandled_exception_handler(request:Request,exc:Exception) ->JSONResponse:
    loggger.exception("unhandled exception at %s %s",request.method,request.url.path)
    return JSONResponse(
        status_code = 500,
        content={"code":"internal_error","message":"服务内部错误"}
    )

#注册到fastAPI中，当框架收到这个类型的异常，会发给对应的函数处理
def register_error_handler(app:FastAPI)->None:
    app.add_exception_handler(AppException,_app_exception_handler)
    app.add_exception_handler(Exception,_unhandled_exception_handler)