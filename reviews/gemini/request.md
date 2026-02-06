# Run Gemini review for current changes

This workspace includes the patch you can feed to Gemini:
- `reviews/gemini/changes.diff`

And the prompt text:
- `reviews/gemini/prompt.txt`

Suggested command (run outside the Codex sandbox):
```bash
cd /Users/geoff/Documents/Projects/BAYESIANQC
gemini -p "$(cat reviews/gemini/prompt.txt)" < reviews/gemini/changes.diff > reviews/gemini/latest.md
```

Notes:
- If Gemini is configured for interactive auth, run it once interactively first (without `-p`) to complete login, then rerun the command above.
- If your environment doesn’t allow shell command substitution, paste the prompt directly with `-p`.
