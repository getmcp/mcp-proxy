# MCP Proxy

```mermaid
flowchart LR
transport[STDIO / SSE]
c1["Claude Desktop"] ---> transport
c2["Cursor"] ---> transport
c3["Windsurf"] ---> transport
transport ---> proxy[MCP Proxy]
proxy ---> mcp1[MCP 1]
proxy ---> mcp2[MCP 2]
proxy ---> mcpn[MCP ...]
```

```shell
npx @modelcontextprotocol/inspector
```