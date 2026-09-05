# Operations

**When to read**: when deploying, restarting, backing up or diagnosing the running instance
**Code**: `<deploy script>`, `<launcher>`
**Related**: [auth](auth.md), [logging](logging.md)

---

## Host

<Machine, address on the tailnet, port, neighbouring services it depends on.>

## Launcher and environment

<Process manager (Task Scheduler task name), the launcher file, every env var it sets. Never paste secrets; say where they live.>

## Deploy

<What is deployed (tag / branch), the exact command, how to verify (health endpoint, version field).>

## Restart and health

<Restart command, health check, where to look when it is down.>

## Backup

<What to back up, how often, how to restore.>

## Incidents

- <YYYY-MM-DD> — <what happened, cause, what changed>
