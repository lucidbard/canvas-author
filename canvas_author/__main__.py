"""
Entry point for running canvas_author.server as a module.

This allows running: python -m canvas_author.server
without triggering RuntimeWarning about sys.modules.
"""

from .server import main

if __name__ == "__main__":
    main()
