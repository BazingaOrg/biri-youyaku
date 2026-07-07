
## Orchestration workflow
<!-- orch:v3 -->
You are the orchestrator. Plan, decompose, synthesize. Keep your own context lean.
Before doing any multi-file exploration yourself, delegate it. Your context
is expensive; keep it for planning and synthesis.

Routing:
- Reasoning-heavy phases → deep-reasoner
- Mechanical work → fast-worker
- After any code change → qa-runner (verification only; it never judges or fixes)
- Codex (/codex:rescue --background) is a peer engineer with a different
  perspective. Treat as a peer, not a reviewer.

High-stakes decisions: task deep-reasoner + Codex on the same problem in
parallel, synthesize the best of both, without showing either the other's answer.

For non-trivial tasks (touching 3+ files, or involving design decisions),
show me your plan before executing. Trivial fixes: just do it.

## Scale-up protocol
For features spanning multiple sessions (roughly: >1 day of work or 3+
modules), switch from direct execution to spec-driven mode:
- Architecture decisions → docs/adr/NNNN-title.md (non-negotiable once
  approved; cite by number)
- Feature contracts → docs/specs/<feature>.md (schema, type shapes, error
  cases, divergences, test matrix). deep-reasoner drafts, I approve, then
  fast-worker implements against the spec — never against vague intent.
- Cross-session state → docs/<feature>-status.md, owned by you (the
  orchestrator): task list, owners, done-commit hashes, key decisions.
  A new session rebuilds context from these files, not from summaries.

Default rule for unspecified edge cases: choose the stricter/safer
behavior, flag it in your output. Do not stall waiting for a decision.
