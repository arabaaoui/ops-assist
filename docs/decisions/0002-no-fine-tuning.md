# Decision 0002 — No fine-tuning for now

The fictional incident corpus is small and its contents change. Keep knowledge in retrieval-augmented generation (RAG), so documents can be reviewed and updated independently of model weights. Shape behavior with instructions, skills and the validated report schema. Use configurable profiles and LiteLLM routing to compare model sizes and providers without changing the application.

`ops-assist eval run` measures a profile against the versioned incident dataset, producing per-case checks and a pass rate. Its literal checks are incomplete proxies for meaning and evidence; review reports and errors as well. Establish an acceptance threshold for the use case before comparing results: neither a threshold nor an expected pass rate is assumed here. Obtain observed rates from `eval run`, including repeats, and record the dataset version, prompt, profile and settings used.

Reopen this decision if the measured pass rate remains below the agreed threshold on the dataset with the best prompt and comparable retrieval settings. First inspect failures, improve the prompt, skills, schema and evidence; consider fine-tuning only if those changes and an appropriate profile do not meet the threshold. Compare a candidate against the same dataset and a separately maintained holdout before deciding whether its operational cost and risks are justified.
