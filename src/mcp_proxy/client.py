import logging
from contextlib import AsyncExitStack
from typing import Optional
import os

from mcp_proxy.types import McpServerConfig
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool, Resource, Prompt, ListToolsResult, ListPromptsResult, ListResourcesResult

logger = logging.getLogger(__name__)


class McpClient:

    def __init__(self, config: McpServerConfig):
        self.config = config
        self.exit_stack = AsyncExitStack()
        self.session: Optional[ClientSession] = None
        self.id = config.name

    async def connect(self):
        logger.info(f"Connecting to MCP server... {self.config.command} {self.config.name}")
        args = [self.config.name, *self.config.args]
        command = self.resolve_command_path(self.config.command)
        params = StdioServerParameters(
            command=command,
            args=args,
            env=self.config.env,
        )
        stdio, write = await self.exit_stack.enter_async_context(stdio_client(params))
        self.session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
        await self.session.initialize()

    async def list_tools(self) -> ListToolsResult:
        result = await self.session.list_tools()
        tools = list(map(lambda tool: Tool(name=f"{self.id}.{tool.name}", description=tool.description,
                                           inputSchema=tool.inputSchema, model_config=tool.model_config), result.tools))
        return ListToolsResult(tools=tools)

    async def list_prompts(self) -> ListPromptsResult:
        try:
            result = await self.session.list_prompts()
            prompts = list(map(lambda prompt: Prompt(name=f"{self.id}.{prompt.name}", description=prompt.description,
                                                     arguments=prompt.arguments, model_config=prompt.model_config),
                               result.prompts))
            return ListPromptsResult(prompts=prompts)
        except Exception as e:
            logger.warning("Error listing prompts, %s: %s", self.id, e)
            return ListPromptsResult(prompts=[])

    async def list_resources(self) -> (list[Resource], str):
        try:
            result = await self.session.list_resources()
            return result.resources, self.id
        except Exception as e:
            logger.warning("Error listing resources, %s: %s", self.id, e)
            return [], self.id

    async def cleanup(self):
        await self.exit_stack.aclose()

    @staticmethod
    def resolve_command_path(command: str) -> str:
        name = f"{command.upper()}_PATH"
        path = os.environ.get(name)
        if path is not None and len(path) > 0:
            logger.info(f"Using {command}={path}")
            return path
        return command
