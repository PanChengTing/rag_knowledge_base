from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

def hash_password(plain:str)->str:
    return bcrypt.hashpw(plain.encode("utf-8"),bcrypt.gensalt()).decode("utf-8")

#验证密码是否正确
def verify_password(plain:str,hashed:str)->bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"),hashed.encode("utf-8"))
    except ValueError:
        return False

#jwt对USER_ID进行签名，给一个有有效期不可伪造的访问令牌
def create_access_token(subject:str)->str:
    # subject传入的是user_id字符串
    if not settings.jwt_secret:
        raise UnauthorizedError("服务端没有配置JWT secret，无法签发token")
    now = datetime.now(timezone.utc)
    payload = {
        "sub":subject,
        "iat":int(now.timestamp()),
        "exp":int((now+timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload,settings.jwt_secret,algorithm=settings.jwt_algorithm)

#解码访问令牌中的userid,校验签名，识别请求是谁发起的
def decode_access_token(token:str)->str:
    if not settings.jwt_secret:
        raise UnauthorizedError("服务端未配置JWT secret")
    try:
        payload = jwt.decode(
            token,settings.jwt_secret,algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("无效的访问凭证") from exc

    subject= payload.get("sub")
    if not isinstance(subject,str) or not subject:
        raise UnauthorizedError("无效的访问凭证")
    return subject