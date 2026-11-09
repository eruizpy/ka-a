# LLM entry point

Start every ka-a consultation here, regardless of model or provider. This directory
holds the canonical AI-facing guidance and project context. It is not a runtime AI
service and does not contain credentials or copies of operational data.

## Reading order

1. Read [AGENTS.md](AGENTS.md) for the repository-wide contributor and safety rules.
2. Read [CONTEXT.md](CONTEXT.md) for confirmed owner decisions and the source map.
3. Read the [project README](../README.md), then the specification and source files
   relevant to the question or requested change.
4. For real-hardware questions, read the [Pi guide](../docs/RASPBERRY_PI.md),
   [wiring contract](../docs/HARDWARE.md), and [validation limits](../docs/VALIDATION.md).

## Discovery across providers

Root [AGENTS.md](../AGENTS.md) is a minimal routing file for clients that discover
that filename. The actual rules live here. For clients that do not load root AGENTS
files automatically, configure `llm/README.md` as their starting context, or attach
this file plus `llm/AGENTS.md` and `llm/CONTEXT.md` explicitly. A folder alone cannot
force an external LLM to load instructions.

Keep AI-specific navigation, handoffs, and context here. Reference canonical source
rather than duplicating it in provider-specific rule files. Product specs remain
under `specs/`; operator docs and validation evidence remain under `docs/`; code
remains under `src/`. Those are shared project artifacts, not private AI configuration.

## Keeping context accurate

Verify Git state and relevant source at the start of work. Treat historical test
results as recorded evidence, not a current passing run. Update context when an
owner decision or implementation contract changes. Do not invent hardware readings,
plant requirements, live AWS status, or physical acceptance.

Never store passwords, private keys, certificates, Wi-Fi details, local configuration,
SQLite databases, raw transcripts containing private information, or generated
runtime artifacts in this directory.
