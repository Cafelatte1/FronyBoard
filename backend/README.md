# FronyBoard

An MCP server that gives AI agents (Claude Code and friends) a first-class project
tracker: roadmap → quarterly periods → months → tasks in one SQLite file, a schema +
rule validation gate before every write, retrospectives that close a period, and a
read-only web dashboard for humans.

<!-- mcp-name: io.github.Cafelatte1/fronyboard -->

## Install

Requires [uv](https://docs.astral.sh/uv/).

```
claude mcp add FronyBoard -- uvx fronyboard
```

Any MCP client that can launch a stdio command works the same way: the command is
`uvx fronyboard`. Data is written to `%LOCALAPPDATA%\Frony\FronyBoard\data`
(`~/.Frony/FronyBoard/data` where `LOCALAPPDATA` is unset); set `AIRA_DATA_DIR` to
relocate it.

Full documentation, the data model, the 20 tools and the shared-server mode live in
the repository: https://github.com/Cafelatte1/FronyBoard
