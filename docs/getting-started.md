# Getting started in ten minutes

This path assumes Python 3.12 and the project's dependencies are already installed in `.venv`. Installation with `uv sync` needs package access; the steps below need neither a network nor a model. Run them from the repository root with fictional data.

1. Inspect the command line: `.venv/bin/ops-assist --help`. Expected: available commands include `triage`, `eval` and `redteam`.
2. Run `.venv/bin/ops-assist triage`. Expected: alerts and evidence from a recorded incident, without a model call.
3. Run `OPS_ASSIST_TEST_ASYNC_TICK=1 scripts/demo.sh`. Expected: an injected fictional timeout, an investigation trace, an automatically confirmed simulated rollback, and a separate uncertain report. The automatic approval is part of the simulation, not a real human decision.
4. Run `.venv/bin/ops-assist eval list`. Expected: the versioned fictional incident set; listing does not evaluate an actual model.
5. Read [workshop 41](../ateliers/41-de-bout-en-bout/README.md) and [known limits](known-limits.md). To investigate with a real model later, configure an existing LiteLLM profile and its provider separately; that path can use the network and incur costs.

The deployment manifests are examples, not an installation procedure. They require an image, external secret provisioning, authentication, network configuration and a proxy that rewrites the loopback address in the agent card. They have not been deployed by the offline checks.
