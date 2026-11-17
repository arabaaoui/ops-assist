"""Offline checks for the agent registry declaration."""

import asyncio
from pathlib import Path

import yaml
from google.adk.tools.base_toolset import BaseToolset

from ops_assist.agent import build_agent
from ops_assist.config import _load_profiles
from ops_assist.security import TOOL_ACCESS

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_matches_agent_and_policy(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_TOOLS", "inprocess")
    catalog = yaml.safe_load((ROOT / "catalog-info.yaml").read_text())
    assert catalog["apiVersion"] == "backstage.io/v1alpha1"
    assert catalog["kind"] == "Component"
    assert catalog["metadata"]["name"] == "ops-assist"
    spec = catalog["spec"]
    assert spec["type"] and spec["lifecycle"] and spec["owner"]
    declaration = spec["agent"]
    entries = declaration["tools"]
    declared = {entry["name"]: entry["access"] for entry in entries}
    assert len(declared) == len(entries)

    async def discover():
        names = set()
        for topology in ("single", "experts"):
            agent = build_agent(allow_writes=True, topology=topology)
            for member in (agent, *agent.sub_agents):
                for tool in member.tools:
                    if isinstance(tool, BaseToolset):
                        names.update(item.name for item in await tool.get_tools())
                    else:
                        names.add(getattr(tool, "name", None) or tool.__name__)
        return names

    names = asyncio.run(discover())
    assert set(declared) == names
    assert declared == {name: TOOL_ACCESS.get(name, "write") for name in names}
    assert {name for name, access in TOOL_ACCESS.items() if access == "write"} <= {
        name for name, access in declared.items() if access == "write"
    }
    assert declaration["purpose"] and declaration["rights"]
    budget = declaration["monthly_budget"]
    assert budget["amount"] > 0 and budget["currency"] and budget["enforcement"]
    profiles = _load_profiles(ROOT / "src/ops_assist/data/profiles.yaml")
    assert declaration["models_by_profile"] == {
        name: profile["models"] for name, profile in profiles.items()
    }
    for key in ("evaluations", "behavior_changelog"):
        assert (ROOT / declaration[key]).is_file()
