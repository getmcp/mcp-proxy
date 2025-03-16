from typing import Optional

from pydantic import BaseModel


class McpServerConfig(BaseModel):
    id: Optional[str] = None
    command: str
    args: list[str] = []
    env: dict[str, str] = {}

    def display_name(self) -> str:
        return self.package
