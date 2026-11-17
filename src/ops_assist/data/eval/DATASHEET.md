# Datasheet: fictional incident evaluation set

## Motivation

This dataset supports reproducible, offline evaluation of incident investigations and disciplined abstention when observations do not support a cause.

## Composition

Version 1.1.0 contains six fictional recordings. Each has a question, alert, metric series, logs, changes (possibly empty), and a separate answer key with status, cause, evidence sources and forbidden conclusions. Four cases retain causal links as accepted hypotheses with `hypotheses_only`; one case deliberately lacks sufficient evidence and expects `insufficient_data`. `ops-assist eval run` (step 23) scores reports using a structured, lexical heuristic that accepts the recorded status and hypothesis without demanding an unproven causal conclusion. The manifest checksum covers the questions and recording files, including answer keys.

## Collection

The scenarios were authored for the workshop; they are synthetic, not collected from people, systems, production incidents or external datasets. No personal data or actual credentials are intended.

## Intended use

Use for local exercises and regression checks. Compare an investigation against its answer key only outside agent-accessible sources. Update the version, changelog and checksum when changing questions or recordings. Published versions are checked against `published.yaml` at load time. After editing, calculate the new checksum with `python -c "import yaml; from ops_assist.evaluation_dataset import MANIFEST, checksum; print(checksum(yaml.safe_load(MANIFEST.read_text())))"`, then update the manifest and add the new version and checksum to `published.yaml` without changing existing entries.

## Limits

Six curated cases do not represent operational diversity or establish production accuracy. Evidence and labels are authored together, with no independent adjudication. The checks detect exact textual leakage, not paraphrases or conceptual overlap. The checksum and local registry enforce a versioning convention; neither is a signature or protects against deliberate modification of both files. The recordings and questions are public, so this is not a secret benchmark.

## Owner and maintenance

The ops-assist maintainers own the dataset, review changes and maintain version history in the manifest. This datasheet follows the motivation, composition, collection, use and maintenance questions of Datasheets for Datasets.
