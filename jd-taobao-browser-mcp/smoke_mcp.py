import anyio

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> None:
    params = StdioServerParameters(
        command=".venv/Scripts/python.exe",
        args=["server.py"],
        cwd=".",
        env={
            "PLAYWRIGHT_HEADLESS": "false",
            "BROWSER_CHANNEL": "msedge",
            "BROWSER_PROFILE_DIR": "./.browser-profile",
            "ARTIFACTS_DIR": "./artifacts",
            "ALLOW_STATE_CHANGING_ACTIONS": "false",
            "PYTHONPATH": ".",
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=20) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            status = await session.call_tool("browser_status", {})
            print("server", init.server_info.name)
            print("tool_count", len(tools.tools))
            print("tools", ",".join(tool.name for tool in tools.tools))
            print("browser_status", status.content)


if __name__ == "__main__":
    anyio.run(main)
