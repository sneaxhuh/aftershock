import json
import os
import sys
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class GraphTools:
    """Real MCP transport, capability discovery and tool invocation."""

    def __init__(self, store, run):
        self.store, self.run = store, run
        self.stack = AsyncExitStack()

    async def __aenter__(self):
        environment = {
            **os.environ,
            "GRAPH_PREFIX": self.store.base_prefix,
            "AFTERSHOCK_TENANT": self.store.tenant,
            "MCP_RUN_ID": self.run["id"],
        }
        try:
            reader, writer = await self.stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "aftershock.mcp_server"],
                        env=environment,
                    )
                )
            )
            self.session = await self.stack.enter_async_context(
                ClientSession(reader, writer)
            )
            await self.session.initialize()
            result = await self.session.list_tools()
            self.tools = {tool.name: tool for tool in result.tools}
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *args):
        await self.stack.aclose()

    def callbacks(self, names):
        functions = {}
        for name in names:

            async def call(arguments, tool_name=name):
                result = await self.session.call_tool(tool_name, arguments)
                if result.isError:
                    message = next(
                        (item.text for item in result.content if item.type == "text"),
                        "MCP tool failed",
                    )
                    raise ValueError(message)
                value = result.structuredContent
                if value is None:
                    text = next(
                        (item.text for item in result.content if item.type == "text"),
                        "{}",
                    )
                    value = json.loads(text)
                self.store.message(
                    self.run,
                    "mcp",
                    "tool_result",
                    {"tool": tool_name, "arguments": arguments, "result": value},
                )
                return value

            functions[name] = call
        return functions
