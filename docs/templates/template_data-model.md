# Data model

**When to read**: when changing a stored schema, a validation rule, or the storage layout
**Code**: `<store / validation modules>`
**Related**: [architecture](architecture.md)

---

## Storage layout

<Where the data root is, how it is organised, one tree listing.>

## Schemas

<One block per file or table: fields, types, required vs optional, an example.>

## Invariants and validation

<Rules the write gate enforces. Say which are errors (write rejected) and which are warnings.>

## Ids and timestamps

<Who issues them, format, timezone.>

## Migration policy

<How schema changes reach existing data: migration script, tolerated legacy shape, or rewrite-on-save.>
