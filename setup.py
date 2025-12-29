from setuptools import setup, find_packages

setup(
    name="canvas-mcp",
    version="0.1.0",
    packages=find_packages(include=["canvas_mcp*"]),
    install_requires=[
        "canvasapi>=3.0.0",
        "mcp>=1.0.0",
        "python-dotenv>=1.0.0",
        "PyYAML>=6.0",
        "premailer>=3.10.0",
    ],
    entry_points={
        "console_scripts": [
            "canvas-mcp=canvas_mcp.cli:main",
        ],
    },
)
