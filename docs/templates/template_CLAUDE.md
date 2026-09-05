<!-- Template: copy to the repo root as CLAUDE.md (or AGENTS.md), fill the <...> slots, delete this comment. -->
# CLAUDE.md

## Project

<Name>: <what the software does, one or two sentences>
<If data lives outside the repo: its location and the env var that moves it. Delete otherwise.>

## Layout

- `<dir>/` — <role> (<language / build tool>)
  - `<key file>` — <what it owns>
  - `<key file>` — <what it owns>
- `<dir>/` — <role>. <relation to other dirs, how build output is handled>

## Commands (from the repo root)

- Test: `<command>`
- <Run / dev server>: `<command>`
- <Build>: `<command>` — <caveats, e.g. whether the output is committed>

## Deploy

<Where and how it runs: host, process manager>
<What triggers a deploy: branch or tag; what does not deploy>
Procedure: <steps, or the doc that has them>
<Delete this section if the project is not deployed.>

## Docs

`docs/INDEX.md` lists every doc with when to read it. Read the matching doc before changing <auth / schema / deploy / ...> and update it in the same branch.

## FronyBoard

This project is tracked by FronyBoard (project key: <KEY>).
Manage tasks through the FronyBoard MCP tools, following the FronyBoard server instructions.
Task tags: <where the work lands, e.g. frontend / backend / infra / docs>, plus
<what kind it is, e.g. design / test / bug>. Reuse these rather than coining a synonym.
