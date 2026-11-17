"""Isolated ADK skills plus MCP scenario, executed by test_mcp with a hard timeout."""

import asyncio
import json
import os

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

import ops_assist.agent as agent_module
from ops_assist.agent import build_agent
from ops_assist.config import load_settings
from ops_assist.report import IncidentReport


class Model(BaseLlm):
    """Exercise discovery, loading, a remote tool, then a report."""

    model: str = "scripted-mcp-skills"
    seen: list = []

    async def generate_content_async(self, llm_request, stream=False):
        """Choose the next scripted action based on tool responses."""
        responses = [
            p.function_response
            for content in llm_request.contents
            for p in content.parts or []
            if p.function_response
        ]
        names = ("list_skills", "load_skill", "get_alerts")
        if len(responses) < len(names):
            name = names[len(responses)]
            args = {"skill_name": "latency"} if name == "load_skill" else {}
            part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        else:
            self.seen.extend(response.response for response in responses)
            alerts = responses[-1].response["structuredContent"]["alerts"]
            report = {
                "summary": f"{len(alerts)} alerts.",
                "status": "hypotheses_only",
                "facts": [{"statement": a["summary"], "source": a["source"]} for a in alerts],
                "hypotheses": [],
                "unknowns": ["mechanism"],
            }
            part = types.Part(text=json.dumps(report))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


async def scenario():
    """Run the actual tool loop and close its MCP client in the same task."""
    os.environ["OPS_ASSIST_TOOLS"] = "mcp"
    original = agent_module.StdioServerParameters

    def params_with_test_path(**kwargs):
        if "PYTHONPATH" in os.environ:
            kwargs["env"]["PYTHONPATH"] = os.environ["PYTHONPATH"]
        return original(**kwargs)

    agent_module.StdioServerParameters = params_with_test_path
    agent = build_agent(load_settings(env={}))
    model = Model(seen=[])
    agent.model = model
    runner = InMemoryRunner(agent=agent, app_name="ops_assist")
    try:
        session = await runner.session_service.create_session(app_name="ops_assist", user_id="u")
        message = types.Content(role="user", parts=[types.Part(text="Investigate latency")])
        async for _ in runner.run_async(user_id="u", session_id=session.id, new_message=message):
            pass
        session = await runner.session_service.get_session(
            app_name="ops_assist", user_id="u", session_id=session.id
        )
        assert "latency" in str(model.seen[0]) and "errors-5xx" in str(model.seen[0])
        assert model.seen[1]["skill_name"] == "latency"
        assert "get_metric" in model.seen[1]["instructions"]
        assert model.seen[2]["structuredContent"]["status"] == "ok"
        assert IncidentReport.model_validate(session.state["report"]).summary == "2 alerts."
    finally:
        await runner.close()
    print("MCP_SKILLS_OK")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(scenario(), timeout=30))
