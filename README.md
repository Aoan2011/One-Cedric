# One Cedric

Claude Code / OpenCode-inspired local agent for working with files and tools.

## Install

```powershell
python -m pip install -e ".[all,gateway]"
one-cedric
```

The terminal menu uses the arrow keys and Enter. CLI Chat contains New session,
My sessions, and Chat settings. A new session asks for its access mode and
action-confirmation preference. The WebUI is available from Gateway.

## Tool execution

Python tools run with the current user's operating-system permissions. Cedric
shows the code and asks for approval before each CLI execution, even when
auto-confirm is enabled. The subprocess timeout still applies. Only run code
you trust.

Downloads with a known size use `alive-progress`; other tools show their name,
elapsed time, and a 24-cell track with a short orange segment that glides and
fades at 10 FPS. Tool results are displayed in framed cards in the terminal and
expandable output panels in the WebUI.

## MCP servers, hooks, and custom tools

Integrations are stored in `~/.one-cedric/integrations.json` and can be managed
from the MCP servers, Hooks, and Tools screens. MCP servers use the standard
stdio transport. A server entry has this shape:

```json
{
  "mcp_servers": {
    "example": {
      "command": "uvx",
      "args": ["some-mcp-server"],
      "env": {},
      "enabled": true
    }
  },
  "hooks": [],
  "custom_tools": {}
}
```

Use the MCP screen's test action to start a server and discover its tools.
MCP tools require confirmation before execution. Hook commands receive a JSON
object on stdin; supported events are `before_tool` and `after_tool`. Hook
failures are reported rather than ignored.

The Tools screen can generate a command-backed custom tool with the configured
model. Generated scripts are saved under `~/.one-cedric/custom_tools/` and are
enabled immediately. They run as the current user; generated custom tools
require confirmation by default. Review generated code before use.

## Accessibility

The terminal UI supports reduced motion with
`ONE_CEDRIC_REDUCED_MOTION=1`. The WebUI supports dark/light themes, larger
text, keyboard focus indicators, and reduced-motion preferences.
