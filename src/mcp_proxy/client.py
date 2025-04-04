import asyncio
import logging
import os
import uuid
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Optional

import mcp.client.stdio
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.types import Tool, Prompt, ListToolsResult, ListPromptsResult, Resource
from mcp_proxy.types import McpServerConfig

logger = logging.getLogger(__name__)


class McpClient:

    def __init__(self, config: McpServerConfig):
        self.write = None
        self.read = None
        self.config = config
        self.session: Optional[ClientSession] = None
        self.connected = False
        self.id = config.id or uuid.uuid4().hex
        self.status = "created"
        self.exit_stack = AsyncExitStack()

    async def connect(self):
        logger.info(f"Connecting to MCP server... {self.config.id}: {self.config.command}")
        args = []
        for arg in self.config.args:
            import re
            if re.match(r'^\{[a-zA-Z_][a-zA-Z0-9_]*\}$', arg):
                env_var = arg[1:-1]
                env_value = os.environ.get(env_var)
                if env_value is not None:
                    args.append(env_value)
                else:
                    args.append(arg)
            else:
                args.append(arg)
        command = self.resolve_command_path(self.config.command)
        envs = mcp.client.stdio.get_default_environment()
        if self.config.env is not None:
            envs.update(self.config.env)
        params = StdioServerParameters(
            command=command,
            args=args,
            env=envs,
        )
        timeout = os.getenv("MCP_PROXY_CONNECT_TIMEOUT", 10)

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(params))
        self.read, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.read, self.write, read_timeout_seconds=timedelta(timeout)))
        task = asyncio.create_task(self.session.initialize())
        self.status = "connecting"
        done, pending = await asyncio.wait([task], timeout=timeout, return_when=asyncio.FIRST_EXCEPTION)
        self.connected = len(done) == 1
        if len(pending) > 0:
            logger.error(f"Connected MCP server failed: {self.exit_stack.pop_all()}")
            self.status = "error"
            for t in pending:
                t.cancel()
            self.read.close()
            self.write.close()
            await self.exit_stack.aclose()
        else:
            logger.info(f"Connected MCP server: {self.id}")
            self.status = "running"

    async def list_tools(self) -> ListToolsResult:
        try:
            result = await self.session.list_tools()
            tools = list(map(lambda tool: Tool(name=f"{self.id}/{tool.name}", description=tool.description,
                                               inputSchema=tool.inputSchema, model_config=tool.model_config),
                             result.tools))
            return ListToolsResult(tools=tools)
        except BaseException as e:
            logger.warning("Error listing tools, %s: %s", self.id, e)
            return ListToolsResult(tools=[])

    async def list_prompts(self) -> ListPromptsResult:
        try:
            result = await self.session.list_prompts()
            prompts = list(map(lambda prompt: Prompt(name=f"{self.id}/{prompt.name}", description=prompt.description,
                                                     arguments=prompt.arguments, model_config=prompt.model_config),
                               result.prompts))
            return ListPromptsResult(prompts=prompts)
        except BaseException as e:
            logger.warning("Error listing prompts, %s: %s", self.id, e)
            return ListPromptsResult(prompts=[])

    async def list_resources(self) -> (list[Resource], str):
        try:
            result = await self.session.list_resources()
            resources = list(map(lambda resource: Resource(name=f"{self.id}/{resource.name}", uri=resource.uri,
                                                           description=resource.description, mimeType=resource.mimeType,
                                                           model_config=resource.model_config), result.resources))
            return resources, self.id
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
