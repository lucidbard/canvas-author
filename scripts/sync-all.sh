#!/bin/bash
# Sync all course directories with Canvas
#
# Usage: ./scripts/sync-all.sh [pull|push|status]
#
# Expects:
#   - CANVAS_API_TOKEN and CANVAS_DOMAIN environment variables set
#   - Course directories in ./courses/ with .canvas.json files

set -e

COMMAND=${1:-status}
COURSES_DIR=${COURSES_DIR:-./courses}

# Check for required tools
if ! command -v canvas-mcp &> /dev/null; then
    echo "Error: canvas-mcp not found. Install with: pip install -e ."
    exit 1
fi

if ! command -v pandoc &> /dev/null; then
    echo "Warning: pandoc not installed. Some features may not work."
fi

# Check for environment variables
if [ -z "$CANVAS_API_TOKEN" ] || [ -z "$CANVAS_DOMAIN" ]; then
    if [ -f .env ]; then
        echo "Loading .env file..."
        export $(grep -v '^#' .env | xargs)
    else
        echo "Error: CANVAS_API_TOKEN and CANVAS_DOMAIN must be set"
        exit 1
    fi
fi

# Find and process all course directories
for course_dir in "$COURSES_DIR"/*/; do
    if [ -f "${course_dir}.canvas.json" ]; then
        course_name=$(jq -r '.course_name // .course_id' "${course_dir}.canvas.json")
        echo ""
        echo "=== $course_name ==="
        echo "Directory: $course_dir"

        case $COMMAND in
            pull)
                canvas-mcp pull --dir "$course_dir" --force
                ;;
            push)
                canvas-mcp push --dir "$course_dir"
                ;;
            status)
                canvas-mcp status --dir "$course_dir"
                ;;
            *)
                echo "Unknown command: $COMMAND"
                echo "Usage: $0 [pull|push|status]"
                exit 1
                ;;
        esac
    fi
done

echo ""
echo "Done!"
