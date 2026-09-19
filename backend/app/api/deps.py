from typing import Annotated
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.core.exceptions import UnauthorizedError,PermissionDeniedError
from app.db.models import User, UserStatus
from app.core.security import decode_access_token
from app.db.repositories.user_repo import UserRepository
from app.services.permission_service import is_admin
from app.core.log_config import settings
from app.core.rate_limiter import get_rate_limiter

DbSession = Annotated[AsyncSession,Depends(get_session)]

#拆分出token访问凭证来，authorization是啥从哪里来？好像是前端发过来的
def _parse_bearer_token(authorization:str|None)->str:
    if not authorization:
        raise UnauthorizedError("请先登录")
    scheme,_,token = authorization.partition(" ")
    if scheme.lower()!="bearer" or not token:
        raise UnauthorizedError("无效访问凭证")
    return token

#从前端的Header取出相应的数据，传输给这个函数
#前端请求-》Authorization请求头-》Header（...）-》_parse_bearer_token
# ->decode_access_token ->得到用户ID-》查数据库-》返回user对象-》验证是否为管理员（is_admin）
# 其中header之前的操作都由fastapi执行，annotated声明该从哪里找对应的数据
async def get_current_user(
        session:DbSession,
        authorization:Annotated[str|None,Header(alias="Authorization")] = None
)->User:
    """
    从Bearer token 截取出token来，再从token取出用户ID，从数据库中找到用户，
    校验用户的各种状态
    """
    token = _parse_bearer_token(authorization)
    subject = decode_access_token(token)

    try:
        from uuid import UUID
        user_id = UUID(subject)
    except (ValueError,TypeError) as exc:
        raise UnauthorizedError("无效的访问凭证") from exc

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise UnauthorizedError("用户不存在或已被删除")
    if user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("账户已被禁用")
    return user

#验证当前用户是否为admin，登录上后加上验证是否为管理员
async def get_current_admin(
        user:Annotated[User,Depends(get_current_user)],
)->User:
    if not is_admin(user):
        raise PermissionDeniedError("仅管理员可访问")
    return user

#根据当前用户计算最长流量
async def enforce_rate_limit(
        user:Annotated[User,Depends(get_current_user)],
)->None:
    if not settings.rate_limit_enabled:
        return
    await get_rate_limiter().check(f"user:{user.id}")

CurrentUser = Annotated[User,Depends(get_current_user)]
CurrentAdmin = Annotated[User,Depends(get_current_admin)]
RateLimited = Annotated[None,Depends(enforce_rate_limit)]