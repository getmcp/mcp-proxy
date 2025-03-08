import logging
import os

import argparse

from mcp_proxy.server import serve

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Create mcp servers proxy."
    )
    parser.add_argument("-c", "--config", type=str, default="mcp-servers.yaml")
    parser.add_argument("-t", "--type", type=str, default="stdio", choices=["stdio", "sse"])
    args = parser.parse_args()
    is_sse = args.type == "sse"
    pid_path = os.getenv("PROXY_PID_PATH")
    if pid_path is not None:
        with open(pid_path, "w") as f:
            f.write(str(os.getpid()))
    else:
        logger.info("Pid: %d", os.getpid())
    serve(args.config, is_sse)


if __name__ == "__main__":
    main()
