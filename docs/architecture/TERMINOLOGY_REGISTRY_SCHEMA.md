# Terminology Registry Schema

## Purpose

The terminology registry is the authoritative catalog of project terminology. It is not a translation dictionary. Each entry defines ownership, identity, presentation mapping, and lifecycle rules.

The registry allows Host and game modules to reference the same terminology contracts without moving game-specific concepts into Core.

## Registry entry

Each term record must contain:

| Field | Purpose |
| --- | --- |
| id | Stable identifier that survives wording changes |
| class | Native Game Term, Trainer Product Term, Internal Domain Term, or Compatibility Alias |
| owner | Subsystem responsible for meaning and lifecycle |
| zh_CN | Chinese presentation mapping when exposed |
| en | English presentation mapping when exposed |
| source | Origin of the term (game localization, product vocabulary, internal contract) |
| allowed_surfaces | Where this term may appear |
| forbidden_surfaces | Where this term must not appear |
| status | Lifecycle state |
| aliases | Previous or compatibility names |

## Example

```yaml
id: hades.boon
class: NativeGameTerm
owner: Hades2Module
source: official_game_localization
zh_CN: "祝福"
en: "Boon"
allowed_surfaces:
  - Hades2_UI
  - Hades2_catalog
forbidden_surfaces:
  - Core_API
status: active
aliases: []
```

## Identity rules

- IDs are stable; display text may change.
- Localization changes do not rename internal identity.
- Aliases must point to one canonical ID.
- Duplicate IDs with different ownership are invalid.

## Ownership rules

Host may consume presentation metadata but does not own game terminology.

A module owns native game terms and game-specific presentation. Core owns generic product vocabulary only.

## Lifecycle

Registry status values:

- `active`: canonical term.
- `deprecated`: retained for migration only.
- `removed`: no longer accepted except historical references.

Migration follows:

canonical entry → compatibility alias → caller migration → alias removal.

## Future implementation

A02 implementation may move this schema into machine-readable form. The schema must preserve the ownership and surface restrictions defined by A01.
