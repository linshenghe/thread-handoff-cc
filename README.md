# thread-handoff-cc

Claude Code plugin — records CC session results to `MASTER_CONTROL.md` for seamless handoff to Codex.

## What it does

When you finish a task in Claude Code, run:

```
/thread-handoff Fixed the data loading bug in analysis.R
```

This appends a structured entry to `MASTER_CONTROL.md` in your project root:

```markdown
## [CC] Fixed the data loading bug in analysis.R

- **Time**: 2026-06-20 14:30
- **Branch**: fix/data-loader
- **Commit**: a1b2c3d
- **Files touched**: scripts/analysis.R, tests/test_analysis.R

### Summary

- Replaced read.csv with fread for 10x speedup
- Added encoding detection for UTF-8/Big5 files
- Updated test expectations

### For Codex

The encoding parameter is now explicit in config.R — check that before changing anything.
```

Codex opens the project, reads `MASTER_CONTROL.md`, and knows exactly what CC did.

## Install

### 1. Add the marketplace

In Claude Code, run:

```
/plugin marketplace add https://github.com/linshenghe/thread-handoff-cc
```

### 2. Install the plugin

```
/plugin install thread-handoff@linshenghe-tools
```

Or browse: `/plugin` → Discover → find `thread-handoff`.

### 3. Use it

```
/thread-handoff <what you just did>
```

## Structure

```
thread-handoff-cc/
├── .claude-plugin/
│   ├── marketplace.json
│   └── plugin.json
├── skills/
│   └── thread-handoff/
│       └── SKILL.md
├── README.md
└── LICENSE
```

## License

MIT
