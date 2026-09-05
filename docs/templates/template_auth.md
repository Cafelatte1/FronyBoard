# Authentication

**When to read**: when changing how a request is authenticated or which channel serves it
**Code**: `<auth middleware / introspection client>`
**Related**: [http-api](http-api.md), [operations](operations.md)

---

## Credentials

<Each credential type: who holds it, how it is issued and revoked (FronyAuth), what it may do.>

## Channels

<Each way in (MCP, JSON API, static UI) and which credential it takes.>

## Verification flow

<Request → middleware → FronyAuth introspection → caller identity on the request. Env vars involved.>

## Failure handling

<What happens when FronyAuth is unreachable, when a token is unknown, when a session expires. Fail-open or fail-closed, and why.>
