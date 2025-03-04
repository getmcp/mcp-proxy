from pydantic import BaseModel


class McpServerConfig(BaseModel):
    command: str
    package: str
    args: list[str] = []
    env: dict[str, str] = {}

    def display_name(self) -> str:
        return self.package
