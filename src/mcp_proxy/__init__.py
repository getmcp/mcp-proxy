import logging

from mcp_proxy.server import serve

logging.basicConfig(level=logging.INFO)


def main():
    serve()
