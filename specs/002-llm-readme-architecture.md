# LLM context isolation and project documentation

## Outcome and baseline

The owner requests a dedicated `llm/` directory for AI-facing instructions and
context, a separate recommended shopping list in the README, and a detailed
software/stack/architecture README with a technical diagram.

Baseline `611e45c`: full contributor/AI rules are in root `AGENTS.md`; no LLM
directory exists. The README has a short feature overview and links to a hardware
BOM, but no shopping section, stack table, or architecture diagram.

## Acceptance criteria

1. Canonical AI guidance lives in `llm/AGENTS.md`, with a provider-neutral entry
   point and source-backed context in `llm/`. A minimal root `AGENTS.md` routes
   discoverable agent entry points there without duplicating the rules.
2. Operational docs, functional specifications, validation records, and code stay
   in their existing product directories. They are not AI-private files.
3. The README separates recommended purchases from software, setup, and architecture;
   includes quantities, compatible interfaces, Amazon lookup links, optional items,
   exclusions, and the existing USD 150-300 hardware-only budget. Do not imply an
   unverified Amazon cart, probe fit, or final price.
4. The stack and architecture describe the actual Python implementation. A GitHub
   Mermaid diagram distinguishes the web process, SQLite, single-owner controller,
   sensors, motor drivers/pumps, simulation, and optional outbound-only AWS telemetry.
   No cloud actuation, lamp switching, or completed physical validation is invented.
5. All local documentation links resolve, the Mermaid diagram renders, and the
   diff contains documentation only. Preserve existing contributor/safety rules.

## Validation and test plan

- Compare routes, configuration, controller, storage, cloud adapter, pyproject,
  installer, and systemd units before describing their contracts.
- Check Markdown local links and anchors, render Mermaid, visually inspect the
  generated diagram, check Markdown formatting, and run `git diff --check`.
- Compare the relocated rule body with the baseline to detect accidental policy loss.
- Product unit/integration/Playwright tests do not apply: no Python, frontend,
  dependency, database, configuration, or deployment behavior changes in this task.
  The previous product evidence remains in `docs/VALIDATION.md` and is not rerun
  or presented as newly executed.

## Risks and guardrails

Some providers discover only root instructions; retain the minimal routing file
and explicitly document manual entry for clients that do not follow it. A directory
does not redirect every LLM automatically. Keep credentials, certificates, local
data, and private hardware configuration out of `llm/`. A shopping reference is not
proof of compatibility, availability, commissioning, or a closed hardware budget.

## Completion record

Completed on 2026-11-09:

- Moved the canonical rule body to `llm/AGENTS.md`; a byte comparison against
  `611e45c:AGENTS.md` confirms that no existing rule was changed or lost.
- Added the provider-neutral LLM entry point/context and retained only the small
  discovery router at root. Shared product/operator docs remain in place.
- Expanded the README with a separate hardware-only shopping list, checked planning
  subtotals, compatible interfaces, stack, service/data/API descriptions, and a
  native GitHub Mermaid diagram. Unpriced safety parts and optional lighting are
  explicitly outside the indicative subtotal; no Amazon checkout is claimed.
- A one-off local Markdown checker verified **44 local links/anchors across all
  six changed Markdown files**, including rule routing and the hardware pin-map link.
- Rendered the extracted diagram with `@mermaid-js/mermaid-cli@11.12.0` and local
  Chromium, then visually inspected the PNG. The final layout uses native Mermaid
  top-to-bottom flow for README display; no external design file was created.
- `npx --yes prettier@3.6.2 --check README.md AGENTS.md 'llm/*.md' specs/002-llm-readme-architecture.md`
  and `git diff --cached --check` passed.
- Confirmed that the diff contains Markdown only. Product unit/integration/browser
  tests were not rerun, as no runtime or dependency behavior changed. Their earlier
  results remain clearly labeled as historical product evidence.

No equipment, AWS resources, deployments, or OS images were changed.
