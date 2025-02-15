import logging
import os
import sys
from mcp_proxy.server import serve

logging.basicConfig(level=logging.INFO)


def main():
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = os.environ.get("MCP_PROXY_CONFIG") or "mcp-servers.json"
    serve(config_path)
