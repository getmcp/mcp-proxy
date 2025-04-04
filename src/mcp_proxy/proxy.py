import asyncio
import json
import logging

import yaml
from mcp.types import Tool, Prompt, TextContent, ImageContent, EmbeddedResource, GetPromptResult, Resource, \
    ReadResourceResult
from mcp_proxy.client import McpClient
from mcp_proxy.types import McpServerConfig
from pydantic import AnyUrl

logger = logging.getLogger(__name__)


class McpProxy:
    def __init__(self, config_path: str):
        logger.info(f"Loading config from {config_path}")
        with open(config_path, 'r', encoding='utf-8') as stream:
            if config_path.endswith('yaml'):
                config = yaml.safe_load(stream)
            else:
                config = json.load(stream)
        server_configs = [McpServerConfig(**server) for server in config['servers']]
        self.clients = [McpClient(server_config) for server_config in server_configs]
        routes = {}
        for client in self.clients:
            routes[client.id] = client
        self.routes = routes
        self.resources = {}

    async def connect(self) -> None:
        tasks = []
        for client in self.clients:
            tasks.append(asyncio.create_task(client.connect()))

    async def wait_for_connect(self) -> None:
        tasks = []
        for client in self.clients:
            tasks.append(asyncio.create_task(client.connect()))
        async with asyncio.timeout(30):
            await asyncio.gather(*tasks, return_exceptions=True)

    async def disconnect(self) -> None:
        tasks = [client.cleanup() for client in self.clients]
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1)

    async def list_tools(self) -> list[Tool]:
        tasks = [client.list_tools() for client in self.clients if client.connected]
        if not tasks:
            return []
        responses = await asyncio.gather(*tasks)
        return sum([response.tools or [] for response in responses], start=[])

    async def call_tool(self, name: str, arguments: dict | None = None) -> list[
        TextContent | ImageContent | EmbeddedResource]:
        logger.info("Calling tool %s", name)
        client, tool_name = self.get_client(name)
        response = await client.session.call_tool(tool_name, arguments)
        return response.content

    async def list_prompts(self) -> list[Prompt]:
        tasks = [client.list_prompts() for client in self.clients if client.connected]
        if not tasks:
            return []
        responses = await asyncio.gather(*tasks)
        return sum([response.prompts or [] for response in responses], start=[])

    async def get_prompt(
            self, name: str, arguments: dict[str, str] | None = None
    ) -> GetPromptResult:
        logger.info("Getting prompt %s", name)
        client, prompt_name = self.get_client(name)
        response = await client.session.get_prompt(prompt_name, arguments)
        return response

    async def list_resources(self) -> list[Resource]:
        tasks = [client.list_resources() for client in self.clients if client.connected]
        if not tasks:
            return []
        responses = await asyncio.gather(*tasks)
        all_resources = []
        for resources, client_id in responses:
            all_resources.extend(resources)
            for resource in resources:
                self.resources[resource.uri] = client_id
        return all_resources

    async def read_resource(self, uri: AnyUrl) -> ReadResourceResult:
        logger.info("Reading resource %s", uri)
        if uri not in self.resources:
            raise ValueError(f"Unknown resource {uri}")
        client_id = self.resources[uri]
        client = self.routes[client_id]
        return await client.session.read_resource(uri)

    def get_client(self, name: str) -> (McpClient, str):
        segments = name.split("/")
        client_id = segments[0]
        if client_id in self.routes:
            return self.routes[client_id], segments[1]
        raise ValueError(f"Unknown client {client_id}")
