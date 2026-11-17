"""Expose the investigator through the ADK A2A application."""

import hmac
import os

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    HTTPAuthSecurityScheme,
    SecurityRequirement,
    SecurityScheme,
    StringList,
)
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .agent import build_agent


def build_card(port: int = 8000, *, token: str | None = None) -> AgentCard:
    """Describe the investigation capability and its local JSON-RPC endpoint."""
    return AgentCard(
        name="ops_assist",
        description="Investigates incidents using alerts, metrics, logs and changes.",
        version="0.1.0",
        supported_interfaces=[
            AgentInterface(
                url=f"http://127.0.0.1:{port}/", protocol_binding="JSONRPC", protocol_version="1.0"
            )
        ],
        capabilities=AgentCapabilities(streaming=True),
        security_schemes=(
            {
                "bearer": SecurityScheme(
                    http_auth_security_scheme=HTTPAuthSecurityScheme(scheme="bearer")
                )
            }
            if token
            else {}
        ),
        security_requirements=(
            [SecurityRequirement(schemes={"bearer": StringList()})] if token else []
        ),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="investigate",
                name="Investigate an incident",
                description="Investigate an incident question and return a sourced report.",
                tags=["incident", "investigation"],
                examples=["Why is payment slow?"],
            )
        ],
    )


class BearerMiddleware(BaseHTTPMiddleware):
    """Protect all endpoints except public agent-card discovery."""

    def __init__(self, app, token: str):
        """Store the expected authorization header."""
        super().__init__(app)
        self._expected = ("Bearer " + token).encode("utf-8")

    async def dispatch(self, request, call_next):
        """Reject unauthenticated requests before they reach A2A routes."""
        if not (request.method == "GET" and request.url.path == "/.well-known/agent-card.json"):
            header = request.headers.get("authorization", "").encode("utf-8")
            if not hmac.compare_digest(header, self._expected):
                return JSONResponse(
                    {"error": "Unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)


def create_app(port: int = 8000, agent=None):
    """Create the A2A ASGI application; allow injection for offline tests."""
    token = os.environ.get("OPS_ASSIST_A2A_TOKEN") or None
    app = to_a2a(agent or build_agent(), agent_card=build_card(port, token=token))
    if token:
        app.add_middleware(BearerMiddleware, token=token)
    return app


def serve(port: int = 8000) -> None:
    """Serve A2A on the loopback interface."""
    import uvicorn

    uvicorn.run(create_app(port), host="127.0.0.1", port=port)
