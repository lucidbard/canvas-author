#!/bin/bash
# Start Canvas Author MCP Server in HTTP mode
# This script starts the server in the background and can be used
# for development or manual server management.
#
# For production, use the systemd service instead:
#   systemctl --user enable canvas-author-server
#   systemctl --user start canvas-author-server

set -e

# Load Canvas credentials from environment or prompt
if [ -z "$CANVAS_API_TOKEN" ]; then
    echo "Error: CANVAS_API_TOKEN environment variable not set"
    echo "Please set it in your shell profile or .env file"
    exit 1
fi

if [ -z "$CANVAS_DOMAIN" ]; then
    CANVAS_DOMAIN="webcourses.ucf.edu"
    echo "Using default Canvas domain: $CANVAS_DOMAIN"
fi

# Server configuration
HOST="${FASTMCP_HOST:-127.0.0.1}"
PORT="${FASTMCP_PORT:-8000}"

echo "Starting Canvas Author MCP Server..."
echo "URL: http://$HOST:$PORT/mcp"
echo ""
echo "To stop the server, use: pkill -f 'canvas_author.server'"
echo ""

# Start server in background
export FASTMCP_HOST="$HOST"
export FASTMCP_PORT="$PORT"
python3 -m canvas_author.server --http &

SERVER_PID=$!
echo "Server started with PID: $SERVER_PID"
echo "Logs will appear below. Press Ctrl+C to stop."
echo ""

# Wait for server to be ready
sleep 2

# Check if server is running
if ps -p $SERVER_PID > /dev/null; then
    echo "Server is running successfully!"
    echo ""
    echo "Test with: curl http://$HOST:$PORT/mcp"
    echo ""

    # Keep script running and show logs
    wait $SERVER_PID
else
    echo "Error: Server failed to start"
    exit 1
fi
