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
        async with ClientSession(read, write, read_timeout_seconds=30) as session:
            await session.initialize()
            start = await session.call_tool("browser_start", {})
            status = await session.call_tool("browser_status", {})
            close = await session.call_tool("browser_close", {})
            print("browser_start", start.content)
            print("browser_status", status.content)
            print("browser_close", close.content)


if __name__ == "__main__":
    anyio.run(main)
