import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource, Prompt, GetPromptResult, Resource, \
    ReadResourceResult, TextResourceContents, BlobResourceContents, ReadResourceRequest, ServerResult
from pydantic import AnyUrl
from mcp_proxy.proxy import McpProxy
from starlette.applications import Starlette
from starlette.routing import Route, Mount


def serve() -> None:
    server = Server("mcp-proxy")
    sse = SseServerTransport("/messages/")

    proxy = McpProxy("mcp-servers.yaml")

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

    async def handle_sse(request):
        async with sse.connect_sse(
                request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )

    routes = [
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ]

    server.request_handlers[ReadResourceRequest] = read_resource
    starlette_app = Starlette(routes=routes, on_startup=[proxy.connect], on_shutdown=[proxy.disconnect])
    uvicorn.run(starlette_app, host="0.0.0.0", port=1598, timeout_graceful_shutdown=5, log_level='info')
