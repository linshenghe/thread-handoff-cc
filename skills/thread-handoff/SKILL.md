---
name: thread-handoff
description: Record what Claude Code just did to MASTER_CONTROL.md so Codex knows the latest state. Use when the user says "record this", "handoff", "log to master control", or after completing a task that Codex will continue.
argument-hint: "<what was done>"
disable-model-invocation: true
allowed-tools: Bash(git *) Bash(ls *) Read
---

## Current state

- Branch: !`git branch --show-current 2>/dev/null || echo "(not a git repo)"`
- Last commit: !`git log -1 --oneline 2>/dev/null || echo "(none)"`
- Changed files: !`git diff --name-only 2>/dev/null || echo "(none)"`

## Instructions

Append a handoff entry to `MASTER_CONTROL.md` in the project root. If the file does not exist, create it.

Use this exact format:

```markdown
## [CC] $ARGUMENTS

- **Time**: <current timestamp in YYYY-MM-DD HH:MM format>
- **Branch**: <branch name>
- **Commit**: <last commit hash or "(none)">
- **Files touched**: <comma-separated list, or "(none)">

### Summary

<2-4 bullet points summarizing what was done, what changed, and any decisions made>

### For Codex

<1-2 sentences: what Codex should know or do next, if anything>
```

Rules:
- The `[CC]` prefix in the heading marks this as a Claude Code entry, distinct from Codex entries.
- Always prepend new entries at the TOP of `MASTER_CONTROL.md` (newest first), after any existing frontmatter or title line.
- If `MASTER_CONTROL.md` already has a `# Master Control` title or similar, keep it at the top and insert the new entry right after it.
- Keep the summary concise — Codex will scan this, not read a novel.
- If `$ARGUMENTS` is empty, ask the user what was done before writing.
