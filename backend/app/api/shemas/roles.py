from pydantic import BaseModel,Field

class RoleCreate(BaseModel):
    name:str = Field(min_length=1,max_length=64)
    description:str = Field(default="",max_length=256)
    permission_tags:list[str]=Field(default_factory=list)

class RoleUpdate(BaseModel):
    description:str|None =Field(default=None,max_length=256)
    permission_tags:list[str]|None =None