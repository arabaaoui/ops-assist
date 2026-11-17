# Behaviour changelog

Entries describe versioned behaviour changes; historical evaluation results are only stated when recorded.

## 2026-11-17 — fingerprint 42d79c521b4b503a

Change: identify the current default profile, prompts, skills, schema, scorer and dataset together. Why: make behavioural builds traceable. Evaluation: offline regression suite (see CI); no live model evaluation claimed.

## 2026-11-17 — scoring and report contract (0cf5b11, 237e43b, 9549617)

Change: introduce structured scoring and citation warnings, then tighten the scorer. Why: assess report quality and flag unsupported citations. Evaluation: historical live evaluation not recorded.

## 2026-11-17 — cloud profiles (78b2f3f)

Change: add cloud deployment profiles. Why: configurable providers and deployment locations. Evaluation: historical live evaluation not recorded.

## 2026-11-17 — retrieval instructions (750b9eb, 9549617)

Change: update investigation prompt for knowledge retrieval and bounded agentic search. Why: ground investigations in relevant documents. Evaluation: historical live evaluation not recorded.

## 2026-11-17 — gateway profile (4a6f16a)

Change: add gateway profile. Why: provider fallback through a configurable gateway. Evaluation: historical live evaluation not recorded.

## 2026-11-17 — investigation skills (1b19605)

Change: add latency and 5xx skills. Why: provide focused investigation guidance. Evaluation: historical live evaluation not recorded.

## 2026-11-17 — model profiles (2013053)

Change: add provider and fallback profiles. Why: avoid a single model provider. Evaluation: historical live evaluation not recorded.

## 2026-11-17 — initial prompt and profile (e578ae3, f87f88a)

Change: introduce the investigation prompt and local profile. Why: establish the agent's initial behaviour. Evaluation: historical live evaluation not recorded.
