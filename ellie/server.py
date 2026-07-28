"""FastAPI server for Ellie agent."""
import json
import sys
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import StreamingResponse
    import uvicorn
except ImportError:
    print("Server dependencies not installed. Run: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

from .cli import build_agent, build_arg_parser
from .runtime import Ellie

app = FastAPI(title="Ellie API", version="1.0.0")

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    return _agent


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
