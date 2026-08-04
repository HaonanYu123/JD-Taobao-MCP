# Security notes

- Keep `ALLOW_STATE_CHANGING_ACTIONS=false`.
- Do not provide account passwords, SMS codes, payment passwords, bank card data, or identity numbers to the MCP client.
- Complete login and CAPTCHA challenges directly in the visible browser window.
- The browser profile directory contains login state. Do not commit, upload, or share it.
- Do not point `BROWSER_PROFILE_DIR` at your normal Chrome or Edge profile.
- Keep the server local. If Streamable HTTP mode is used, bind and firewall it as a local-only service unless authentication is added.
- Review MCP tool calls in the client. The supplied Codex example uses `default_tools_approval_mode = "prompt"`.
