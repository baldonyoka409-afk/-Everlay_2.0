"""
Web API for Everlay - FastAPI application.
"""
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

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

logger = get_logger(__name__)


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


@app.get("/api/sessions", response_model=List[SessionInfo])
async def list_sessions():
    """List all active sessions."""
    return session_manager.list_sessions()


@app.get("/api/sessions/{conversation_id}", response_model=SessionInfo)
async def get_session(conversation_id: str):
    """Get session info."""
    session = session_manager.get_session(conversation_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionInfo(
        conversation_id=session["conversation_id"],
        agent=session["agent_type"],
        model=session["agent"].model,
        message_count=session["message_count"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
    )


@app.delete("/api/sessions/{conversation_id}")
async def delete_session(conversation_id: str):
    """Delete a session."""
    if session_manager.delete_session(conversation_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Session not found")


@app.post("/api/sessions/{conversation_id}/clear")
async def clear_session(conversation_id: str):
    """Clear session history."""
    session = session_manager.get_session(conversation_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session["agent"].clear_history()
    session["message_count"] = 0
    session["updated_at"] = datetime.utcnow()

    return {"success": True}


@app.get("/api/models")
async def list_models():
    """List available models from OpenRouter."""
    try:
        client = get_client()
        models = await client.list_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Web UI
@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the web UI."""
    with open("web/templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=settings.app_debug,
    )