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
from mcp_proxy.proxy import McpProxy
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

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

    server.request_handlers[ReadResourceRequest] = read_resource

    if is_sse:
        logger.info("Starting SSE server")
        transport = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with transport.connect_sse(
                    request.scope, request.receive, request._send
            ) as streams:
                await server.run(
                    streams[0], streams[1], server.create_initialization_options()
                )

        async def handle_servers(request):
            results = list(map(lambda client: {"id": client.id, "status": client.status}, proxy.clients))
            return JSONResponse(results)

        routes = [
            Route("/servers", endpoint=handle_servers),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=transport.handle_post_message)
        ]

        async def handle_http_exception(request: Request, exc: Exception):
            logger.error(f"Error during request: {exc}")
            return JSONResponse({"detail": exc.args}, status_code=500)

        async def shutdown():
            logger.info("Shutting down server...")
            try:
                await asyncio.wait_for(proxy.disconnect(), timeout=1)
            except asyncio.TimeoutError:
                logger.error("Timeout during shutdown, forcing exit")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")

        exception_handlers = {
            Exception: handle_http_exception,
            TypeError: handle_http_exception,
            RuntimeError: handle_http_exception,
        }

        starlette_app = Starlette(debug=True, routes=routes, on_startup=[proxy.connect], on_shutdown=[shutdown],
                                  exception_handlers=exception_handlers)
        starlette_app = CORSMiddleware(starlette_app, allow_origins=["*"], allow_methods=["POST", "GET"])
        uvicorn.run(starlette_app, host="0.0.0.0", port=1598, log_level='info', timeout_graceful_shutdown=5)
    else:
        logger.info("Starting STDIO server")

        async def run():
            await proxy.wait_for_connect()
            async with mcp.server.stdio.stdio_server() as (read, write):
                _options = server.create_initialization_options()
                # options = InitializationOptions(
                #     server_name=_options.server_name,
                #     server_version=_options.server_version,
                #     capabilities=server.get_capabilities(
                #         notification_options=NotificationOptions(prompts_changed=True, resources_changed=True,
                #                                                  tools_changed=True),
                #         experimental_capabilities={},
                #     ),
                #     instructions=_options.instructions,
                # )
                await server.run(read, write, _options)

        def stop(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown")
            asyncio.get_event_loop().create_task(proxy.disconnect())
            sys.exit(0)

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        asyncio.run(run())
