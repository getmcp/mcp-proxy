import logging

import argparse

from mcp_proxy.server import serve

logging.basicConfig(level=logging.INFO)


def main():
    parser = argparse.ArgumentParser(
        description="Create mcp servers proxy."
    )
    parser.add_argument("-c", "--config", type=str, default="mcp-servers.json")
    parser.add_argument("-t", "--type", type=str, default="stdio", choices=["stdio", "sse"])
    args = parser.parse_args()
    is_sse = args.type == "sse"
    serve(args.config, is_sse)


if __name__ == "__main__":
    main()
