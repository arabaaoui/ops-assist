"""Delegate once to an A2A investigator and validate its untrusted result."""

import asyncio
import math
import os
from collections.abc import AsyncGenerator

from fastapi.openapi.models import HTTPBearer
from google.adk.a2a.agent import RemoteA2aAgent
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.auth.auth_credential import (
    AuthCredential,
    AuthCredentialTypes,
    HttpAuth,
    HttpCredentials,
)
from google.adk.events import Event
from google.genai import types
from pydantic import ValidationError

from ops_assist.report import IncidentReport

MAX_ANSWER_BYTES = 64 * 1024


class OnCallAssistant(BaseAgent):
    """Validate the completed remote output before returning any remote text."""

    timeout_seconds: float = 120.0

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        text = ""
        response = None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async for event in self.sub_agents[0].run_async(ctx):
                    if event.error_message:
                        raise RuntimeError("remote A2A request failed")
                    if event.content:
                        for part in event.content.parts or []:
                            if part.text and not part.thought:
                                if len(part.text.encode("utf-8")) > MAX_ANSWER_BYTES:
                                    raise ValueError("remote A2A answer exceeds 64 KiB")
                                text = part.text
                    metadata = event.custom_metadata or {}
                    if "a2a:response" in metadata:
                        response = metadata["a2a:response"]
            if isinstance(response, dict) and "status" in response:
                state = response.get("status", {}).get("state")
                if state != "TASK_STATE_COMPLETED":
                    raise RuntimeError("remote A2A task did not complete")
                artifacts = response.get("artifacts", [])
                parts = [
                    part.get("text", "")
                    for artifact in artifacts
                    for part in artifact.get("parts", [])
                ]
                if parts:
                    if sum(len(part.encode("utf-8")) for part in parts) > MAX_ANSWER_BYTES:
                        raise ValueError("remote A2A answer exceeds 64 KiB")
                    text = "".join(parts)
            try:
                report = IncidentReport.model_validate_json(text)
            except ValidationError as exc:
                # Do not echo untrusted text or validation input in the error.
                raise ValueError(
                    "remote agent returned an invalid report: "
                    f"{exc.error_count()} validation error(s)"
                ) from exc
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                content=types.Content(
                    role="model", parts=[types.Part(text=report.model_dump_json())]
                ),
                custom_metadata={"a2a:response": response} if response else None,
            )
        except TimeoutError:
            message = f"remote A2A request timed out after {self.timeout_seconds:g} seconds"
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                error_message=message,
                content=types.Content(role="model", parts=[types.Part(text=message)]),
            )
        except (ValueError, RuntimeError) as exc:
            message = str(exc)
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                error_message=message,
                content=types.Content(role="model", parts=[types.Part(text=message)]),
            )

        except Exception:  # noqa: BLE001 - avoid exposing remote exception details
            message = "remote A2A request failed unexpectedly"
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                error_message=message,
                content=types.Content(role="model", parts=[types.Part(text=message)]),
            )


def build_agent(card_url: str | None = None, httpx_client=None) -> OnCallAssistant:
    """Configure a remote agent with an optional bearer credential and deadline."""
    timeout = float(os.environ.get("OPS_ASSIST_A2A_TIMEOUT", "120"))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("OPS_ASSIST_A2A_TIMEOUT must be a positive finite number")
    token = os.environ.get("OPS_ASSIST_A2A_TOKEN")
    auth = {}
    if token:
        auth = {
            "auth_scheme": HTTPBearer(scheme="bearer"),
            "auth_credential": AuthCredential(
                auth_type=AuthCredentialTypes.HTTP,
                http=HttpAuth(scheme="bearer", credentials=HttpCredentials(token=token)),
            ),
        }
    remote = RemoteA2aAgent(
        name="incident_investigator",
        description="Investigate the incident question and return a sourced report.",
        agent_card=card_url
        or os.environ.get(
            "OPS_ASSIST_A2A_CARD_URL", "http://127.0.0.1:8000/.well-known/agent-card.json"
        ),
        httpx_client=httpx_client,
        timeout=timeout,
        **auth,
    )
    return OnCallAssistant(name="oncall_assistant", sub_agents=[remote], timeout_seconds=timeout)


root_agent = build_agent()
