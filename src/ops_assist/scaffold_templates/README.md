# __AGENT_NAME__

This starter uses the ops-assist platform's installed environment and its profiles,
model routing, audit and security policy. It does not make a model call when built.
The example tool returns fictional, bounded evidence; tool results are untrusted.
The skill is an editable document and is not automatically loaded.

Run offline from this directory with the platform's existing virtual environment:

```sh
PYTHONPATH=. /path/to/ops-assist/.venv/bin/python -m pytest -q tests
```

For CI, configure repository variables `OPS_ASSIST_REPOSITORY` and `OPS_ASSIST_REF`
to identify the platform repository and an immutable reviewed revision. The workflow
checks out both repositories and installs the platform's locked environment. The team
owns its tools, prompts, evaluation and review of platform updates. Classify each new
tool in the platform security policy, bound its output and handle errors.
