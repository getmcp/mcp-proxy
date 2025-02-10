from pydantic import BaseModel


class McpServerConfig(BaseModel):
    command: str
    name: str
    args: list[str] = []
