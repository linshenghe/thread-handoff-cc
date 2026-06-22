---
name: thread-handoff
description: Record what Claude Code just did to MASTER_CONTROL.md so Codex knows the latest state. Use when the user says "record this", "handoff", "log to master control", or after completing a task that Codex will continue.
argument-hint: "<what was done>"
disable-model-invocation: true
allowed-tools: Bash(git *) Bash(ls *) Read
---

## Current state

- Session ID: !`echo $CLAUDE_CODE_SESSION_ID`
- Branch: !`git branch --show-current 2>/dev/null || echo "(not a git repo)"`
- Last commit: !`git log -1 --oneline 2>/dev/null || echo "(none)"`
- Changed files: !`git diff --name-only 2>/dev/null || echo "(none)"`

## Instructions

### Step 1: Ensure MASTER_CONTROL.md conforms to the template

Before writing the handoff entry, check if `MASTER_CONTROL.md` exists and conforms to the standard template. If it doesn't exist, create it from the template. If it exists but doesn't match the template structure, reorganize it to conform.

**Standard template:**

```markdown
# Master Control

## 项目信息

- **项目**：<project name>
- **仓库**：<repo url or "(none)">
- **默认分支**：<default branch>

## 活动日志

<!-- [CC] 和 [Codex] 条目按时间倒序插入此处，最新在上 -->

## 当前状态

<!-- 一句话：现在做到哪了、下一步是什么 -->
```

Template rules:
- The three sections (`项目信息`, `活动日志`, `当前状态`) must exist in this order.
- `项目信息` should be filled in once based on project context (repo remote, current branch). If unknown, leave placeholder.
- `活动日志` is where all `[CC]` and `[Codex]` entries go. This section should only contain the handoff entries, no other prose.
- `当前状态` is a living 1-2 sentence summary of where the project is now and what's next. Update it after each handoff entry.
- If the existing file has useful content (old decisions, conflict notes, old thread records) that doesn't fit the template, consolidate it into `当前状态` or append it as a `## 历史记录` section at the bottom. Do NOT silently delete old content.
- If the file already conforms to the template, skip reorganization and go to Step 2.

### Step 2: Write the handoff entry

Insert the new entry into the `## 活动日志` section. **The entry goes AFTER `## 项目信息` and at the TOP of `## 活动日志`** (newest first). Do NOT insert the entry before `项目信息` — the `[CC]` entry is a log item, not file header.

Use this exact format for the entry:

```markdown
## [CC] $ARGUMENTS

- **Time**: <current timestamp in YYYY-MM-DD HH:MM format>
- **Session ID**: <the value from `$CLAUDE_CODE_SESSION_ID` shown in Current state above — do NOT write the placeholder>
- **Branch**: <branch name>
- **Commit**: <last commit hash or "(none)">
- **Files touched**: <comma-separated list, or "(none)">

### Summary

<2-4 bullet points summarizing what was done, what changed, and any decisions made>

### For Codex

<1-2 sentences: what Codex should know or do next, if anything>
```

### Step 3: Verify conformance

After writing, read back `MASTER_CONTROL.md` and verify:
- The three template sections exist in order.
- The new `[CC]` entry is in `活动日志`, at the top.
- `当前状态` has been updated to reflect the latest progress.
- The entry format is correct (all fields present).

If anything is off, fix it before reporting done.
