# Terminology Governance Model

## Purpose

MacGamingTrainer contains several classes of names that historically evolved from different sources: official game vocabulary, user-facing Trainer concepts, implementation identifiers, compatibility names, and temporary development shorthand.

This model establishes ownership before terminology enters code, UI, logs, protocols, paths, fixtures, or documentation.

A01 defines the governance rules. A02 implements the executable terminology registry. The registry is not a translation dictionary; it is the authoritative record of semantic ownership and allowed usage.

## Core principle

Every term must answer four questions:

1. What does this name represent?
2. Who owns its meaning?
3. Where may it appear?
4. What migration state does it have?

A string without ownership is not a governed term.

## Terminology classes

| Class | Owner | Definition | Examples of usage |
| --- | --- | --- | --- |
| Native Game Term | Game module with official game source/reference ownership | Vocabulary defined by the target game or its official localization | Hades boon names, resources, native menu concepts |
| Trainer Product Term | Product UX ownership | Concepts introduced by MacGamingTrainer for user workflows | Feature names, Trainer actions, settings concepts |
| Internal Domain Term | Owning subsystem | Stable engineering vocabulary representing architecture concepts | Feature identity, capability, action, resource, state projection |
| Compatibility Alias | Migration ownership | Temporary mapping from retired or external names to canonical names | Old command names, previous UI labels, migration keys |

## Ownership boundaries

### Game terminology

Game modules own game meaning.

A game module may expose official game terms to presentation layers, but those terms must remain distinguishable from Trainer-created concepts.

Core and Host must not absorb game-specific vocabulary merely because one module currently needs it.

### Product terminology

Trainer Product Terms describe what the application provides. They must not imitate official game language.

A Trainer action that affects a game does not become a game term automatically.

### Internal terminology

Internal Domain Terms are implementation contracts. They exist for code, protocol, diagnostics, tests, and architecture boundaries.

Internal names should prefer stable semantic concepts over temporary UI wording.

### Compatibility terminology

Aliases exist only to support migration. They cannot become new canonical names.

## Surface rules

| Surface | Allowed terminology | Restrictions |
| --- | --- | --- |
| User UI | Native Game Terms and Trainer Product Terms through localization IDs | No raw internal symbols or deprecated aliases |
| User notifications | Presentation terms | Error identity and diagnostic detail remain separate |
| Logs/diagnostics | Internal Domain Terms, stable identifiers, mapped presentation context when needed | Do not create new user vocabulary accidentally |
| Protocol | Stable identifiers and internal domain concepts | Game semantics stay inside game modules |
| Code symbols | Internal Domain Terms | Avoid user-facing names as implementation contracts |
| Paths/packages/artifacts | Owning subsystem terminology | Rename through migration, not destructive replacement |
| Tests/fixtures | Canonical identifiers plus explicit legacy cases | Tests must not preserve deprecated naming as truth |

## Canonical naming rules

1. Official game terminology takes precedence for game-facing concepts.
2. Trainer concepts receive explicit product names.
3. Internal identifiers describe architecture, not presentation copy.
4. Chinese and English user-facing names resolve from the same localization identity.
5. User shorthand is input context only and never automatically becomes canonical terminology.
6. Similar words with different ownership require separate registry entries.

## Relationship with Feature Identity

Terminology governance and feature identity are related but separate.

Feature identity answers:

> What stable capability or action is this?

Terminology governance answers:

> What should humans and systems call this concept, and where is that name valid?

A feature key is not automatically a display name. A display name is not automatically a protocol identifier.

C01 Feature Identity Parity verifies that existing identity boundaries do not drift. It does not replace the terminology registry.

## Migration lifecycle

Terminology changes follow:

```
Proposed term
    ↓
Canonical term introduced
    ↓
Compatibility alias retained where required
    ↓
Callers and surfaces migrated
    ↓
Alias removed
```

A migration must define:

- previous term;
- canonical replacement;
- affected surfaces;
- owner;
- removal condition.

## Registry requirements for A02

Each registry entry should contain at minimum:

- stable term identifier;
- term class;
- canonical English name;
- canonical Chinese name where user-facing;
- owner subsystem;
- source authority;
- allowed surfaces;
- forbidden surfaces;
- aliases;
- migration state.

The registry should allow future validation of:

- missing localization pairs;
- terminology leakage across boundaries;
- deprecated alias usage;
- UI exposure of internal terms.

## Review checklist

Before introducing a new term:

- Is ownership defined?
- Is the term native game vocabulary, Trainer vocabulary, internal vocabulary, or migration-only?
- Does the intended surface allow this class?
- Does an existing canonical term already exist?
- Are zh/en mappings required?
- Is migration from an existing name required?

A term without ownership, surface policy, and lifecycle state is incomplete.
