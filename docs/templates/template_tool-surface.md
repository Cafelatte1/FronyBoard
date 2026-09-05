# MCP tool surface

**When to read**: when adding, renaming or regrouping a tool, or editing the server `instructions=` block
**Code**: `<server module with the @mcp.tool() wrappers>`
**Related**: [data-model](data-model.md)

---

## Tools by group

<Bullet per group: `tool_a`, `tool_b` — what the group covers. The grouping should mirror the workflow, not the code layout.>

## `instructions=` vs tool docstrings

<What the server-wide instructions hold (workflow, cross-tool rules) versus what each docstring holds (arguments, return shape, one-tool pitfalls). Note any length limit the client truncates at.>

## Adding a tool

1. <service function + validation>
2. <wrapper + docstring>
3. <tests>
4. <this doc, README table, version bump>
