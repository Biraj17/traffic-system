# KICKOFF PROMPT — paste this into Claude Code first

Put `CLAUDE.md`, `BUILD_PLAN.md`, and this file in your (empty) project folder, open Claude Code
there, and paste the block below as your very first message. It tells Claude Code to read the plan
and build the whole thing phase by phase, checking in with you at each checkpoint.

---

## Option A — Supervised autonomous (recommended)

> You are building the project described in `CLAUDE.md` and `BUILD_PLAN.md` in this repo. Read both
> files fully before doing anything.
>
> Work through the phases in BUILD_PLAN.md **section 4, in order (Phase 1 → 6, then 7 if time)**.
> For each phase:
> 1. Implement exactly what that phase's prompt specifies, following the architecture, folder layout,
>    and coding standards in CLAUDE.md.
> 2. Write and run the tests for that phase. Run the simulation to confirm it actually works.
> 3. Give me the one-line "you check" command from the plan and a 2-sentence summary of what you did.
> 4. `git commit` the phase with a clear message, then continue to the next phase.
>
> Rules: the controller is the only component that talks to SUMO via TraCI. Never create an unsafe
> green→green transition. Put all tunable numbers in `src/config.py`. If SUMO isn't installed or a
> command fails, stop and tell me exactly what to fix — don't fake results. Default the junction to
> Kalanki, Kathmandu but keep coordinates configurable.
>
> Start with Phase 1 now. Pause after each phase so I can run the check before you continue.

---

## Option B — Fully hands-off (only if you truly can't watch)

Same as Option A, but replace the last line with:

> Do not pause between phases. Build all phases end to end, committing after each. Keep a running
> log in `docs/BUILD_LOG.md` of what you did, every command you ran, every check result, and
> anything I need to verify or fix afterwards. If you hit a blocker you cannot safely resolve
> (e.g. SUMO not installed), record it in the log and continue with whatever does not depend on it.

> ⚠️ Use Option B only if you've installed SUMO and deps first (BUILD_PLAN section 2) — otherwise
> Phase 1 will block on the missing simulator. When you're back, read `docs/BUILD_LOG.md` first.

---

## Mid-build nudges you can reuse
- `The check failed — here's the error: <paste>. Fix it and re-verify before continuing.`
- `Commit this phase and move to the next.`
- `Before continuing, run pytest and show me it's green.`
- `Make the dashboard look more professional and follow the dataviz guidance.`
- `Update docs/BUILD_LOG.md and CLAUDE.md if anything about the architecture changed.`
