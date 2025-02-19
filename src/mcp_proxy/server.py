import asyncio
import logging
import signal
import sys

import mcp.server.stdio
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource, Prompt, GetPromptResult, Resource, \
    ReadResourceResult, ReadResourceRequest, ServerResult
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route, Mount

from mcp_proxy.proxy import McpProxy

logger = logging.getLogger(__name__)


def serve(config_path: str, is_sse: bool) -> None:
    server = Server("mcp-proxy")

    proxy = McpProxy(config_path)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = await proxy.list_tools()
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None = None) -> list[
        TextContent | ImageContent | EmbeddedResource]:
        result = await proxy.call_tool(name, arguments)
        return result

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        prompts = await proxy.list_prompts()
        return prompts

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> GetPromptResult:
        return await proxy.get_prompt(name, arguments)

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        return await proxy.list_resources()

    async def read_resource(req: ReadResourceRequest) -> ServerResult:
        result = await proxy.read_resource(req.params.uri)
        return ServerResult(
            ReadResourceResult(
                contents=result.contents,
            )
        )

    if is_sse:
        logger.info("Starting SSE server")
        transport = SseServerTransport("http://localhost:1598/sse")

        async def handle_sse(request):
            async with transport.connect_sse(
                    request.scope, request.receive, request._send
            ) as streams:
                await server.run(
                    streams[0], streams[1], server.create_initialization_options()
                )

        routes = [
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=transport.handle_post_message),
        ]

        server.request_handlers[ReadResourceRequest] = read_resource
        middleware = [
            Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["POST", "GET"])
        ]
        starlette_app = Starlette(routes=routes, on_startup=[proxy.connect], on_shutdown=[proxy.disconnect],
                                  middleware=middleware)
        uvicorn.run(starlette_app, host="0.0.0.0", port=1598, log_level='info')
    else:
        logger.info("Starting STDIO server")

        async def run():
            await proxy.connect()
            async with mcp.server.stdio.stdio_server() as (read, write):
                await server.run(read, write, server.create_initialization_options())

        def stop(signum, frame):
            # await proxy.disconnect()
            sys.exit(0)

        signal.signal(signal.SIGINT, stop)
        asyncio.run(run())
