# Canvas Author MCP Server

The Canvas Author MCP server can run in two modes:

## 1. Stdio Mode (Legacy)
Used by Claude Code's MCP client configuration. The server is spawned as a subprocess for each VS Code window.

```bash
python -m canvas_author.server --stdio
```

## 2. Streamable HTTP Mode (Recommended)
Run as a shared server that multiple clients can connect to (VS Code extension, web UI, Claude Code instances).

```bash
python -m canvas_author.server --http
```

## Shared Server Architecture

### Why Use a Shared Server?

- **Single source of truth**: One server instance manages all Canvas operations
- **Multiple clients**: VS Code extension, web UI, and Claude Code can all connect
- **Better resource management**: No duplicate API calls or state conflicts
- **Easier debugging**: Single server log instead of multiple subprocesses

### Setup as systemd Service (Recommended for Linux)

1. **Configure your Canvas credentials** in the service file:

```bash
# Edit the service file
nano canvas-author-server.service

# Set your Canvas API token
Environment="CANVAS_API_TOKEN=your_token_here"
```

2. **Install the service**:

```bash
# Copy to systemd user directory
mkdir -p ~/.config/systemd/user
cp canvas-author-server.service ~/.config/systemd/user/

# Enable and start the service
systemctl --user enable canvas-author-server
systemctl --user start canvas-author-server

# Check status
systemctl --user status canvas-author-server

# View logs
journalctl --user -u canvas-author-server -f
```

3. **Configure clients to connect**:

The server will be available at `http://127.0.0.1:8000/mcp`

### Manual Start (Development)

For development or testing, you can use the start script:

```bash
# Set your Canvas credentials
export CANVAS_DOMAIN="webcourses.ucf.edu"
export CANVAS_API_TOKEN="your_token_here"

# Start server
./start-server.sh
```

Or run directly:

```bash
export CANVAS_DOMAIN="webcourses.ucf.edu"
export CANVAS_API_TOKEN="your_token_here"
export FASTMCP_HOST="127.0.0.1"
export FASTMCP_PORT="8000"

python -m canvas_author.server --http
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `streamable-http` | Transport mode: `stdio` or `streamable-http` |
| `CANVAS_DOMAIN` | - | Canvas LMS domain (e.g., `webcourses.ucf.edu`) |
| `CANVAS_API_TOKEN` | - | Your Canvas API token |
| `FASTMCP_HOST` | `127.0.0.1` | HTTP server host |
| `FASTMCP_PORT` | `8000` | HTTP server port |

## Client Configuration

### VS Code Extension

Update the VS Code extension to connect to the shared server instead of spawning a subprocess.

### Claude Code

Add to your MCP client configuration (`~/.config/claude-code/mcp.json`):

```json
{
  "mcpServers": {
    "canvas-author": {
      "transport": "streamable-http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### Web UI

Configure your web application to make HTTP requests to `http://127.0.0.1:8000/mcp`.

## Testing the Server

Once running, test the connection:

```bash
# Check if server is responding
curl http://127.0.0.1:8000/mcp

# You should see MCP protocol responses
```

## Troubleshooting

### Server won't start

- Check if port 8000 is already in use: `lsof -i :8000`
- Verify Canvas credentials are set correctly
- Check logs: `journalctl --user -u canvas-author-server -f`

### Connection refused

- Ensure server is running: `systemctl --user status canvas-author-server`
- Verify firewall isn't blocking localhost connections
- Check the correct port is configured

### API errors

- Verify `CANVAS_API_TOKEN` is valid
- Check `CANVAS_DOMAIN` is correct
- Ensure your Canvas token has appropriate permissions

## Migration Guide

### From stdio (VS Code spawned subprocess) to HTTP (shared server)

1. Start the shared server using systemd service
2. Update VS Code extension to connect via HTTP instead of spawning subprocess
3. Update Claude Code MCP config to use HTTP transport
4. Test that all clients can connect and make tool calls

This ensures all clients share the same server state and avoid duplicate API calls.
