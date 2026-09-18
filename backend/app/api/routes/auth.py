from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.api.shemas.auth import LoginRequest
from app.api.shemas.auth import LoginResponse
from app.services.auth_service import AuthService
from app.core.exceptions import UnauthorizedError
from app.api.shemas.auth import UserRead
from app.services.permission_service import compute_user_permission_tag, is_admin

from app.api.shemas.auth import MeResponse


router = APIRouter(prefix="/auth",tags=["auth"])

@router.post("/login",response_model=LoginResponse,operation_id="login")
async def login(payload:LoginRequest,session:DbSession)->LoginResponse:
    service = AuthService(session)
    user = await service.authenticate(payload.username,payload.password)
    if user is None:
        raise UnauthorizedError("用户名或者密码错误")
    #创建一个token
    token = AuthService.issue_token(user)
    return LoginResponse(
        access_token = token,
        user = UserRead.model_validate(user),
        permission_tags=compute_user_permission_tag(user),
        is_admin = is_admin(user),
    )

@router.get("/me",response_model=MeResponse,operation_id="getCurrentUser")
async def me(user:CurrentUser)->MeResponse:
    return MeResponse(
        user = UserRead.model_validate(user),
        permission_tags=compute_user_permission_tag(user),
        is_admin = is_admin(user),
    )