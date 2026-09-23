# Terminology Governance Model

## Purpose

This document defines the ownership model for terminology used across MacGamingTrainer. A term is a contract between its source meaning and the surfaces where it may appear.

The terminology registry introduced by A02 is the executable source of individual term records. This document defines the classification rules those records must follow.

## Term classes

| Class | Owner | Meaning | Allowed surfaces | Forbidden surfaces |
| --- | --- | --- | --- | --- |
| Native Game Term | Game module / official game localization source | A name defined by the target game | Game-facing UI, game-specific commands, game-specific help, catalog references, bilingual localization IDs | Core abstractions, generic Host APIs, renamed trainer concepts presented as if official |
| Trainer Product Term | Product/Host UX ownership | A user-facing concept introduced by MacGamingTrainer | Host UI, shared UX, settings, user documentation | Native game catalogs, game protocol payloads, pretending to be official game terminology |
| Internal Domain Term | Owning subsystem | Stable implementation concept required by architecture | Code symbols, protocol contracts, internal diagnostics, tests | Direct user presentation unless explicitly mapped through presentation localization |
| Compatibility Alias | Migration ownership | Temporary bridge from old terminology to canonical terminology | Parsers, migration code, compatibility handling | New UI, new code paths, new documentation as canonical naming |

## Ownership rules

1. The owner of a term decides its canonical spelling, lifecycle, and migration path.
2. A term must not cross ownership boundaries without an explicit mapping.
3. User shorthand is an input description, not a canonical term.
4. When a game provides official terminology, game-facing names resolve from the game's localization/reference source.
5. When no official game term exists, use a declared Trainer Product Term or Internal Domain Term according to the intended surface.

## Surface policy

### User presentation

UI labels, menus, notifications, and user-visible messages use presentation terms. They must have a localization identity and must not expose internal implementation vocabulary.

### Diagnostics

Logs and developer diagnostics may use Internal Domain Terms when they improve debugging. Stable error identity and user presentation are separate concerns.

### Code and protocol

Code symbols and protocol fields use Internal Domain Terms or stable identifiers. Game-specific meaning remains inside the owning game module.

### Paths and artifacts

Repository paths, packages, fixtures, and generated artifacts follow the owning subsystem vocabulary. Renames use migration stages rather than destructive bulk changes.

## Migration lifecycle

All terminology migrations follow:

1. Introduce canonical term.
2. Provide compatibility alias where required.
3. Migrate callers and surfaces.
4. Remove deprecated alias after no active dependency remains.

Aliases are migration tools, not permanent alternate names.

## Review checklist for new terms

Before adding a term:

- Identify the owner.
- Classify the term.
- Define allowed surfaces.
- Define forbidden leakage.
- Provide zh/en mapping when exposed to users.
- Record migration status if replacing an existing term.

A term without ownership and surface rules is incomplete.
