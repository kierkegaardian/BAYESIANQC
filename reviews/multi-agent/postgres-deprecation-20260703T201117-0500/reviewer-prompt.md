# Reviewer Prompt

You are reviewing BAYESIANQC for a Postgres-only local/dev runtime cutover.

Please inspect the current workspace diff and this packet. Focus on blocking P0/P1 risks only unless a lower-severity issue is unusually cheap and important to note.

Answer with:

1. Verdict: approve, approve-with-nits, or block.
2. Findings ordered by severity with file/line references where possible.
3. Specific fixes required before the demo/job-search milestone.
4. Any remaining production/lab-readiness gaps that should be documented but are not blockers for local/dev demo.

Important boundaries:

- Do not push or change remotes.
- Do not revert unrelated dirty work.
- SQLite should be rejected for app runtime and allowed only for explicit legacy import/rehearsal input.
- Treat production go-live as out of scope for this local/dev cutover.
