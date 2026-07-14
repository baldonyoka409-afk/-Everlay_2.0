"""
Web API for Everlay - FastAPI application.
"""
import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.config import get_settings
from core.logging_config import setup_logging, get_logger
from core.exceptions import EverlayError
from core.openrouter_client import get_client, close_client, Message
from agents.presets import AgentFactory, DefaultAgent, CodeAgent, ChatAgent
from agents.base import AgentContext, AgentStatus, BaseAgent
from agents.remote_tools import get_remote_tools, RemoteControlTool

logger = get_logger(__name__)

# Global remote control server
_remote_server = None


def get_remote_server():
    global _remote_server
    if _remote_server is None:
        _remote_server = RemoteControlServer()
    return _remote_server


class RemoteControlServer:
    """Manages remote control sessions and WebSocket connections."""

    def __init__(self):
        self.active_sessions: Dict[str, Dict] = {}
        self.websocket_clients: Set[WebSocket] = set()

    async def register_client(self, websocket: WebSocket, session_id: str):
        """Register a new WebSocket client."""
        self.websocket_clients.add(websocket)
        self.active_sessions[session_id] = {
            "websocket": websocket,
            "connected_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
        }
        logger.info(f"Remote client connected: {session_id}")

    async def unregister_client(self, websocket: WebSocket, session_id: str):
        """Unregister a WebSocket client."""
        self.websocket_clients.discard(websocket)
        self.active_sessions.pop(session_id, None)
        logger.info(f"Remote client disconnected: {session_id}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        if not self.websocket_clients:
            return
        data = json.dumps(message)
        disconnected = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_text(data)
            except Exception:
                disconnected.add(ws)
        for ws in disconnected:
            self.websocket_clients.discard(ws)

    def get_status(self) -> dict:
        """Get server status."""
        return {
            "active_sessions": len(self.active_sessions),
            "websocket_clients": len(self.websocket_clients),
            "sessions": [
                {
                    "id": sid,
                    "connected_at": s["connected_at"].isoformat(),
                    "last_activity": s["last_activity"].isoformat(),
                }
                for sid, s in self.active_sessions.items()
            ]
        }


# Pydantic models
class ChatRequest(BaseModel):
    message: str
    agent: str = "default"
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    success: bool
    content: str
    conversation_id: str
    agent: str
    model: str
    usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None


class AgentInfo(BaseModel):
    name: str
    description: str
    model: str
    temperature: float
    max_tokens: int
    tools: List[str]


class SessionInfo(BaseModel):
    conversation_id: str
    agent: str
    model: str
    message_count: int
    created_at: datetime
    updated_at: datetime


# Session management
class SessionManager:
    """Manage user sessions."""

    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.agents: Dict[str, BaseAgent] = {}

    def get_or_create_session(self, conversation_id: str, agent_type: str) -> Dict[str, Any]:
        """Get or create session."""
        if conversation_id not in self.sessions:
            agent = AgentFactory.create(agent_type)
            context = AgentContext(
                agent_id=agent.name,
                conversation_id=conversation_id,
            )
            self.sessions[conversation_id] = {
                "conversation_id": conversation_id,
                "agent_type": agent_type,
                "agent": agent,
                "context": context,
                "message_count": 0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        session = self.sessions[conversation_id]
        session["updated_at"] = datetime.utcnow()
        return session

    def get_session(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID."""
        return self.sessions.get(conversation_id)

    def delete_session(self, conversation_id: str) -> bool:
        """Delete session."""
        if conversation_id in self.sessions:
            del self.sessions[conversation_id]
            return True
        return False

    def list_sessions(self) -> List[SessionInfo]:
        """List all sessions."""
        return [
            SessionInfo(
                conversation_id=s["conversation_id"],
                agent=s["agent_type"],
                model=s["agent"].model,
                message_count=s["message_count"],
                created_at=s["created_at"],
                updated_at=s["updated_at"],
            )
            for s in self.sessions.values()
        ]


session_manager = SessionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan."""
    # Startup
    setup_logging()
    logger.info("Starting Everlay Web API")
    get_client()  # Initialize client
    yield
    # Shutdown
    await close_client()
    logger.info("Shutting down Everlay Web API")


app = FastAPI(
    title="Everlay AI Environment",
    description="Web API for AI agents via OpenRouter",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")


# API Routes
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/agents", response_model=List[AgentInfo])
async def list_agents():
    """List available agent types."""
    agents = []
    for name in AgentFactory.list_types():
        agent = AgentFactory.create(name)
        agents.append(AgentInfo(
            name=agent.name,
            description=agent.system_prompt[:100] + "...",
            model=agent.model,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            tools=list(agent.tools.keys()),
        ))
    return agents


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to an agent."""
    # Validate agent type
    if request.agent not in AgentFactory.list_types():
        raise HTTPException(status_code=400, detail=f"Unknown agent: {request.agent}")

    # Get or create session
    conversation_id = request.conversation_id or str(uuid.uuid4())
    session = session_manager.get_or_create_session(conversation_id, request.agent)

    agent = session["agent"]
    context = session["context"]

    # Override model if provided
    if request.model:
        agent.model = request.model
    if request.temperature is not None:
        agent.temperature = request.temperature
    if request.max_tokens is not None:
        agent.max_tokens = request.max_tokens

    session["message_count"] += 1

    try:
        if request.stream:
            # For streaming, we'd need a different endpoint (WebSocket)
            raise HTTPException(status_code=400, detail="Use WebSocket for streaming")

        result = await agent.run(request.message, context)

        return ChatResponse(
            success=result.success,
            content=result.content,
            conversation_id=conversation_id,
            agent=request.agent,
            model=agent.model,
            usage=result.usage,
            error=result.error,
        )

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/api/chat/stream")
async def chat_stream(websocket: WebSocket):
    """WebSocket endpoint for streaming chat."""
    await websocket.accept()

    try:
        # Receive initial config
        config = await websocket.receive_json()
        request = ChatRequest(**config)

        if request.agent not in AgentFactory.list_types():
            await websocket.send_json({"error": f"Unknown agent: {request.agent}"})
            await websocket.close()
            return

        conversation_id = request.conversation_id or str(uuid.uuid4())
        session = session_manager.get_or_create_session(conversation_id, request.agent)

        agent = session["agent"]
        context = session["context"]

        if request.model:
            agent.model = request.model
        if request.temperature is not None:
            agent.temperature = request.temperature
        if request.max_tokens is not None:
            agent.max_tokens = request.max_tokens

        session["message_count"] += 1

        # Stream response
        async for chunk in agent.run(request.message, context, stream=True):
            await websocket.send_json({
                "content": chunk.content,
                "complete": chunk.metadata.get("complete", False),
                "streaming": chunk.metadata.get("streaming", False),
                "conversation_id": conversation_id,
            })

        await websocket.close()

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()


# ===== Remote Control WebSocket Endpoints =====

@app.websocket("/api/remote/control")
async def remote_control_ws(websocket: WebSocket):
    """WebSocket endpoint for remote PC control."""
    await websocket.accept()
    session_id = str(uuid.uuid4())
    server = get_remote_server()
    await server.register_client(websocket, session_id)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "welcome",
            "session_id": session_id,
            "message": "Connected to Everlay Remote Control",
            "capabilities": [
                "file_manager", "process_manager", "system_control",
                "clipboard", "screen_capture", "shell", "network"
            ]
        })

        while True:
            data = await websocket.receive_json()

            # Update activity
            if session_id in server.active_sessions:
                server.active_sessions[session_id]["last_activity"] = datetime.utcnow()

            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
                continue

            if msg_type == "execute":
                # Execute remote command
                module = data.get("module")
                action = data.get("action")
                params = data.get("params", {})
                request_id = data.get("request_id", str(uuid.uuid4()))

                try:
                    # Get remote control tool
                    tools = get_remote_tools()
                    rc_tool = None
                    for t in tools:
                        if isinstance(t, RemoteControlTool):
                            rc_tool = t
                            break

                    if not rc_tool:
                        raise ValueError("Remote control tool not available")

                    result = await rc_tool.execute(
                        module=data.get("module"),
                        action=action,
                        params=data.get("params", {})
                    )

                    await websocket.send_json({
                        "type": "result",
                        "request_id": request_id,
                        "success": True,
                        "result": result
                    })
                except Exception as e:
                    logger.error(f"Remote execute error: {e}")
                    await websocket.send_json({
                        "type": "result",
                        "request_id": request_id,
                        "success": False,
                        "error": str(e)
                    })
                continue

            elif msg_type == "subscribe":
                # Subscribe to events
                events = data.get("events", [])
                await websocket.send_json({
                    "type": "subscribed",
                    "events": events
                })
                continue

            # Unknown message type
            await websocket.send_json({
                "type": "error",
                "message": f"Unknown message type: {msg_type}"
            })

    except WebSocketDisconnect:
        logger.info(f"Remote control disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Remote control WebSocket error: {e}")
    finally:
        await server.unregister_client(websocket, session_id)


@app.websocket("/api/remote/events")
async def remote_events_ws(websocket: WebSocket):
    """WebSocket for server-sent events (system monitoring)."""
    await websocket.accept()
    session_id = str(uuid.uuid4())
    server = get_remote_server()
    await server.register_client(websocket, session_id)

    try:
        # Send initial system info
        import psutil
        await websocket.send_json({
            "type": "system_info",
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory": dict(psutil.virtual_memory()._asdict()),
            "disk": {p.mountpoint: dict(psutil.disk_usage(p.mountpoint)._asdict())
                     for p in psutil.disk_partitions() if p.fstype},
            "network": dict(psutil.net_io_counters()._asdict()),
        })

        # Send periodic updates
        while True:
            await asyncio.sleep(2)
            await websocket.send_json({
                "type": "metrics",
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "timestamp": datetime.utcnow().isoformat(),
            })

    except WebSocketDisconnect:
        logger.info(f"Events WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Events WebSocket error: {e}")
    finally:
        await server.unregister_client(websocket, session_id)


# REST API for remote control
class RemoteExecuteRequest(BaseModel):
    module: str
    action: str
    params: Dict[str, Any] = {}


@app.post("/api/remote/execute")
async def remote_execute(request: RemoteExecuteRequest):
    """Execute remote command via REST."""
    try:
        tools = get_remote_tools()
        rc_tool = None
        for t in tools:
            if isinstance(t, RemoteControlTool):
                rc_tool = t
                break

        if not rc_tool:
            raise HTTPException(status_code=500, detail="Remote control not available")

        result = await rc_tool.execute(
            module=request.module,
            action=request.action,
            params=request.params
        )

        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Remote execute error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/remote/status")
async def remote_status():
    """Get remote control server status."""
    server = get_remote_server()
    return server.get_status()


@app.get("/api/remote/tools")
async def remote_tools_list():
    """List available remote control tools."""
    tools = get_remote_tools()
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters
            }
            for t in tools
        ]
    }