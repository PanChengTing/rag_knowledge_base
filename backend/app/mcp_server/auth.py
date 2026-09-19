from uuid import UUID

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

from app.core.exceptions import AppException, UnauthorizedError
from app.db.models import User, UserStatus
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.db.repositories.user_repo import UserRepository
from app.services.permission_service import is_admin

#拆分出token访问凭证来，authorization是啥从哪里来？好像是前端发过来的
def _parse_bearer_token(authorization:str|None)->str:
    if not authorization:
        raise UnauthorizedError("请先登录")
    scheme,_,token = authorization.partition(" ")
    if scheme.lower()!="bearer" or not token:
        raise UnauthorizedError("无效访问凭证")
    return token

async def resolve_current_user(ctx:Context)->User:
    request = getattr(ctx.request_context,"request",None)
    if request is None:
        raise ToolError("当前传输不支持鉴权")

    try:
        token = _parse_bearer_token(request.headers.get("authorization"))
        subject = decode_access_token(token)
        user_id = UUID(subject)
    except (AppException,ValueError) as exc:
        raise ToolError(_user_facing_message(exc,default="无效的访问凭证")) from exc

    async with AsyncSessionLocal() as session:
        user= await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise ToolError("用户不存在或已被删除")
    if user.status !=UserStatus.ACTIVE:
        raise ToolError("账号已被禁用")
    return user

def _user_facing_message(exc:Exception,*,default:str)->str:
    if isinstance(exc,AppException):
        return exc.message
    return default

def require_admin(user:User)->None:
    if not is_admin(user):
        raise ToolError("仅管理员可调用此工具")
    