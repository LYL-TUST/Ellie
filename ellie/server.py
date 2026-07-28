"""FastAPI server for Ellie agent."""
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import StreamingResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError:
    print("Server dependencies not installed. Run: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

from .cli import build_agent, build_arg_parser
from .runtime import Ellie
from .workspace import IGNORED_PATH_NAMES

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Ellie API", version="1.0.0")

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    return _agent


def _safe_path(relative: str):
    """Resolve and validate a path stays inside the workspace root."""
    agent = get_agent()
    root = agent.root.resolve()
    resolved = (root / relative).resolve()
    if os.path.commonpath([str(root), str(resolved)]) != str(root):
        raise HTTPException(status_code=403, detail="Path escapes workspace")
    return resolved


@app.get("/files")
async def list_files():
    """List all files in the workspace (tree structure)."""
    agent = get_agent()
    root = agent.root

    def build_tree(dir_path: Path):
        items = []
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return items
        for entry in entries:
            if entry.name in IGNORED_PATH_NAMES or entry.name.startswith("."):
                continue
            if entry.is_dir():
                children = build_tree(entry)
                if children or any(True for _ in entry.iterdir()):
                    items.append({
                        "name": entry.name,
                        "type": "dir",
                        "path": str(entry.relative_to(root)).replace("\\", "/"),
                        "children": children,
                    })
            else:
                items.append({
                    "name": entry.name,
                    "type": "file",
                    "path": str(entry.relative_to(root)).replace("\\", "/"),
                })
        return items

    return {"root": str(root), "tree": build_tree(root)}


@app.get("/file")
async def read_file(path: str = Query(...)):
    """Read a file's content from the workspace."""
    resolved = _safe_path(path)
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"path": path, "content": content, "size": len(content)}


@app.get("/diff")
async def git_diff():
    """Return git diff of current workspace changes."""
    agent = get_agent()
    try:
        result = subprocess.run(
            ["git", "diff", "--no-color"],
            cwd=str(agent.root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        diff_text = result.stdout.strip()
    except Exception as e:
        return {"diff": "", "error": str(e)}
    return {"diff": diff_text}


@app.post("/ask")
async def ask(request: dict):
    """Send a message to Ellie and get a response."""
    agent = get_agent()
    question = str(request.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    stream = bool(request.get("stream", False))

    if stream and hasattr(agent.model_client, "complete_stream"):
        async def generate():
            for chunk in agent.ask_stream(question):
                yield chunk

        return StreamingResponse(generate(), media_type="text/plain")

    try:
        answer = agent.ask(question)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"answer": answer}


@app.get("/sessions")
async def list_sessions():
    """List recent sessions."""
    agent = get_agent()
    return {"current_session": agent.session.get("id", "")}


@app.post("/reset")
async def reset():
    """Reset the current session."""
    agent = get_agent()
    agent.reset()
    return {"status": "reset"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def serve_ui():
    """Serve the web UI."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "UI not found. Place index.html in ellie/static/."}


def create_agent(cwd=".", provider=None, model=None, approval="auto"):
    """Initialize the agent for server mode."""
    global _agent
    parser = build_arg_parser()
    argv = ["--approval", approval]
    if provider:
        argv.extend(["--provider", provider])
    if model:
        argv.extend(["--model", model])
    argv.extend(["--cwd", str(cwd)])
    args = parser.parse_args(argv)
    _agent = build_agent(args)
    return _agent


def run_server(host="127.0.0.1", port=8080, cwd=".", provider=None, model=None, approval="auto"):
    """Start the HTTP server."""
    create_agent(cwd=cwd, provider=provider, model=model, approval=approval)
    uvicorn.run(app, host=host, port=port)
