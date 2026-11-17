"""Run a deterministic offline investigation and simulated approved rollback."""

import asyncio
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from ops_assist.observability import ReplaySource
from ops_assist.report import IncidentReport
from ops_assist.security import SecurityBoundary, make_rollback_tool
from ops_assist.tools import make_tools


class ScriptedModel(BaseLlm):
    """Drive a fixed demonstration, without a provider or model call."""

    model: str = "scripted-demo"

    async def generate_content_async(self, llm_request, stream=False):
        """Inspect tool responses and advance the scripted scenario."""
        responses = [
            p.function_response
            for c in llm_request.contents
            for p in c.parts or []
            if p.function_response
        ]
        if not responses:
            call = types.FunctionCall(name="get_logs", args={"service": "payment-api"})
        elif responses[-1].name == "get_logs":
            call = types.FunctionCall(
                name="rollback_deployment",
                args={"service": "payment-api", "deployment_id": "DEP-2140"},
            )
        else:
            report = IncidentReport.model_validate(
                {
                    "summary": "Simulated rollback completed; causation remains unproven.",
                    "status": "hypotheses_only",
                    "facts": [],
                    "hypotheses": [],
                    "unknowns": ["Whether the deployment caused the incident"],
                }
            )
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text=report.model_dump_json())]
                )
            )
            return
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(function_call=call)])
        )


async def run():
    """Use real replay tools and security callbacks with an in-memory demo client."""
    if os.environ.get("OPS_ASSIST_TEST_ASYNC_TICK") == "1":
        loop = asyncio.get_running_loop()

        def tick():
            loop.call_soon(tick)

        loop.call_soon(tick)
    source = ReplaySource("payment-latency")
    original_logs = source.logs

    def fault(service, *args, **kwargs):
        rows = original_logs(service, *args, **kwargs)
        return [{"service": service, "message": "Injected fictional fault: timeout"}, *rows]

    source.logs = fault
    calls = []
    client = SimpleNamespace(
        rollback_deployment=lambda *args: calls.append(args) or {"status": "ok"}
    )
    boundary = SecurityBoundary(allow_writes=True)
    agent = Agent(
        name="demo",
        model=ScriptedModel(),
        tools=[
            *make_tools(source),
            make_rollback_tool(SimpleNamespace(name="demo"), demo_client=client, boundary=boundary),
        ],
        before_tool_callback=boundary.before,
        after_tool_callback=boundary.after,
        on_tool_error_callback=boundary.error,
    )
    runner = InMemoryRunner(agent=agent, app_name="demo")
    session = await runner.session_service.create_session(app_name="demo", user_id="demo")

    async def execute(message):
        return [
            event
            async for event in runner.run_async(
                user_id="demo", session_id=session.id, new_message=message
            )
        ]

    try:
        events = await execute(types.Content(role="user", parts=[types.Part(text="Investigate")]))
        request = next(
            fc
            for event in events
            for fc in event.get_function_calls()
            if fc.name == "adk_request_confirmation"
        )
        print("Injected fictional fault: timeout")
        for event in events:
            for response in event.get_function_responses():
                if response.name == "get_logs":
                    assert "Injected fictional fault" in str(response.response)
                    print("Trace: get_logs observed the injected fault")
        print("Confirmation: automatically approved for this simulation only")
        response = types.FunctionResponse(
            id=request.id, name=request.name, response={"confirmed": True}
        )
        events += await execute(
            types.Content(role="user", parts=[types.Part(function_response=response)])
        )
        assert calls == [("payment-api", "DEP-2140")]
        print("Trace: rollback_deployment completed on injected demo client")
        uncertain_alerts = await make_tools(ReplaySource("inc-2026-0416"))[0]()
        assert uncertain_alerts["status"] == "ok" and uncertain_alerts["alerts"]
        print("Trace: get_alerts for inc-2026-0416")
        print(
            "Uncertain case:",
            IncidentReport.model_validate(
                {
                    "summary": "Intermittent failures have no established cause.",
                    "status": "insufficient_data",
                    "facts": [
                        {
                            "statement": uncertain_alerts["alerts"][0]["summary"],
                            "source": uncertain_alerts["alerts"][0]["source"],
                        }
                    ],
                    "hypotheses": [],
                    "unknowns": ["Cause; metrics and logs have not been examined"],
                }
            ).model_dump_json(),
        )
        print("Limits: scripted model, fictional observations, no real deployment or causal proof.")
    finally:
        await runner.close()


def main():
    """Isolate audit state for the simulation."""
    with tempfile.TemporaryDirectory() as directory:
        os.environ["OPS_ASSIST_STATE_DIR"] = str(Path(directory) / "state")
        asyncio.run(run())


if __name__ == "__main__":
    main()
