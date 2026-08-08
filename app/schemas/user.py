from pydantic import BaseModel, Field

class RegisterUser(BaseModel):
    username: str = Field(max_length=16, min_length=3, description="用户名")
    password: str = Field(max_length=16, min_length=6, description="密码")