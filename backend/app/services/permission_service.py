from app.db.models import User


WILDCARD_PERMISSION_TAG="*"
ADMIN_ROLE_NAME="admin"

def compute_user_permission_tag(user:User)->list[str]:
    #把用户所有角色的权限合并并去重
    merged:set[str] = set()
    for role in user.roles:
        for tag in role.permission_tags:
            if tag == WILDCARD_PERMISSION_TAG:
                return [WILDCARD_PERMISSION_TAG]
            merged.add(tag)
    return sorted(merged)

def is_admin(user:User)->bool:
    #是否拥有admin角色
    return any(role.name == ADMIN_ROLE_NAME for role in user.roles)
