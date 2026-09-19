# Core Save Management Design

## Status

Approved for implementation on `refactor/save-management`.

## Goal

Move save management from the Hades II module into a reusable Trainer Host/Core subsystem. A game module defines which files are actual game saves and the policy for live operations; Core owns snapshot storage, verification, hot backup, hot-first restore, rollback, staged restore, protocol commands, and the shared save-management UI.

Hades II legacy backup migration is explicitly out of scope. Existing legacy backups are not read, converted, or deleted by this work.

## Product requirements

1. One snapshot represents the complete set of actual save files for one game at one point in time.
2. There are no snapshot categories such as test/manual/automatic.
3. Core never recursively backs up an entire save root by default.
4. Save discovery is declarative first, with an optional game-local provider for games whose real save set cannot be expressed statically.
5. Hot backup is preferred whenever the module allows it.
6. Restore is hot-first when the module allows it. A running game alone is not a reason to defer restore.
7. If the selected save files are actively changing or the module/provider reports them busy, Core may stage the restore when the module enables staged restore.
8. Internal snapshots use directories plus a manifest. ZIP export is not part of this implementation.
9. Core does not automatically delete old snapshots.
10. The save-management UI and its state machine are rewritten as Core/Host functionality. Hades II no longer owns save-manager UI/state/commands.

## Ownership

### Game module

A module declares a `saveManagement` section in `module.json`:

- one or more allowed save roots;
- explicit include patterns for real save files;
- optional provider target;
- whether live backup is allowed;
- restore policy: `hotPreferred` or `stoppedOnly`;
- whether a busy restore may be staged.

The module may implement an optional provider when static patterns are insufficient. A provider may refine the resolved real-save file set and may report a live restore as busy. It does not copy files, write manifests, restore data, manage rollback copies, or manage staged transactions.

### Backend Core

Backend Core owns:

- manifest validation for save declarations;
- save-file resolution and path containment checks;
- snapshot creation, hashing, validation and inventory;
- display-name metadata;
- transactional restore and rollback;
- hot-operation stability checks;
- staged restore persistence;
- generic `core.save.*` protocol commands.

### Trainer Host / Swift Core

Swift Core owns:

- `TrainerSaveManagerModel`;
- generic snapshot decoding;
- save manager presentation state;
- the save manager sheet;
- the Host-level entry point;
- applying a staged restore from the existing target-process exit event.

Game UI must not duplicate save-manager controls.

## Manifest contract

Example:

```json
{
  "saveManagement": {
    "roots": [
      {
        "id": "main",
        "path": "~/Library/Application Support/Example Game",
        "include": ["Profile*.sav", "activeProfile", "saveinfo"]
      }
    ],
    "provider": null,
    "hotBackup": true,
    "restorePolicy": "hotPreferred",
    "stagedRestore": true
  }
}
```

Rules:

- root IDs are lowercase safe identifiers and unique within the game;
- root paths are absolute or `~`-relative user paths after expansion;
- include patterns must be relative and cannot contain `..`;
- an empty include list is invalid;
- symlink save roots or symlink files are rejected;
- provider targets, when present, must stay inside the selected game package;
- runtime public metadata exposes only save capabilities needed by Host, not local filesystem paths.

Hades II uses a declarative definition. Its initial rule set is based on the repository's established real-save fixtures and recovery paths:

```text
root: ~/Library/Application Support/Supergiant Games/Hades II
include:
  Profile*.sav
  activeProfile
  saveinfo
```

No other file below that directory is included unless the declaration is intentionally updated.

## Save resolution

Core converts the module declaration/provider result into a sorted set of logical file references:

```text
(rootID, relativePath, absoluteSourcePath)
```

Every resolved file must:

- be a regular file;
- be contained by its declared root after resolution;
- not be a symlink;
- have a normalized non-empty relative path;
- be unique by `(rootID, relativePath)`.

Declarative resolution uses only explicit include patterns. It never falls back to recursive enumeration.

Provider results pass through the same Core validation. Provider output cannot expand the allowed roots.

## Snapshot format

New snapshots live at:

```text
~/Library/Application Support/MacGamingTrainer/<game-id>/saves/snapshots/<snapshot-id>/
  manifest.json
  files/
    <root-id>/
      <relative paths>
```

The manifest contains only generic data:

```text
schemaVersion
snapshotId
gameId
createdAt
displayName
hot
files[]:
  rootId
  relativePath
  sha256
  size
```

Snapshots have stable physical IDs. Rename edits only `displayName`.

A snapshot is valid only if its manifest is valid, every listed file matches size/hash, no unexpected file exists under `files/`, and no symlink is present.

## Hot backup

If the target process is not running, backup performs one verified snapshot attempt.

If the target process is running:

- when `hotBackup=false`, Core returns a busy error;
- when `hotBackup=true`, Core attempts a live snapshot.

A live attempt:

1. resolves the real-save set;
2. hashes each source before copy;
3. copies only the resolved files;
4. verifies each copied file;
5. verifies the source still has the original hash;
6. resolves the real-save set again;
7. verifies the file set and hashes are unchanged;
8. commits the snapshot manifest only after all checks pass.

A racing live write discards the temporary attempt and retries a small bounded number of times. An incomplete attempt is never listed as a snapshot.

## Restore policy

### stoppedOnly

If the target process is running, Core does not mutate save files. If staged restore is enabled, the requested transaction is staged; otherwise Core returns busy.

### hotPreferred

If the target process is stopped, Core restores immediately.

If it is running, Core performs an optimistic preflight:

- resolve current real-save files;
- verify a short stable sample of the file set and hashes;
- allow an optional provider to report busy.

If stable, Core attempts transactional live restore. The fact that the game has a process or an open descriptor is not by itself considered busy.

The filesystem cannot prove that an arbitrary game will never write the file again. Therefore the generic contract is "stable now, provider did not veto, transaction verified", not "OS guarantees the game no longer owns the file".

## Transactional restore

Before any mutation Core validates the target snapshot.

For every restore Core creates a temporary rollback snapshot of the current real-save set. This rollback copy is transaction-internal and is not shown in the snapshot inventory.

When the user enables "preserve current save before restore", Core additionally creates one normal persistent snapshot after preflight succeeds and before target mutation.

Core then:

1. revalidates that current files still equal the rollback baseline;
2. copies each target file to a temporary file in the destination directory;
3. verifies its hash;
4. atomically replaces the destination file;
5. removes only currently resolved real-save files that do not exist in the target snapshot;
6. verifies the resolved target set and hashes;
7. for a live restore, performs one bounded post-write stability verification.

Core never removes or renames the declared save root.

If the target transaction fails, Core restores the rollback file set. If rollback also fails, the rollback directory is preserved and its path is included in the error. Core must never delete the last recoverable copy.

If a live restore fails specifically because the files became busy/racing before mutation, and staged restore is enabled, Core records the transaction instead of partially restoring it.

## Staged restore

Staged state lives under the Core game save-data directory, not in a game module directory.

It stores:

- snapshot ID;
- whether a persistent pre-restore snapshot is requested;
- staged timestamp.

Only one pending restore exists per game.

The existing `TrainerTargetProcessMonitor` exit event is the trigger. Host sends `core.save.apply_staged` when the target transitions to stopped. There is no save-manager polling timer and no LLDB/Lua polling.

Corrupt staged metadata is quarantined and ignored.

## Generic protocol

Reserved Host/Core commands:

```text
core.save.list
core.save.backup
core.save.rename
core.save.delete
core.save.open_folder
core.save.restore
core.save.cancel_staged
core.save.apply_staged
```

The JSONL router handles these before dispatching game-specific commands.

Results expose generic snapshot rows and pending-restore state. Game adapters do not implement these commands.

## Swift ownership and backend session

The current architecture hides `TrainerBackendSession` inside the Hades model. Save management cannot become Host-owned while that remains true.

The App therefore creates the single backend session and injects it into both:

- the active game model;
- `TrainerHostView`, which creates the Core `TrainerSaveManagerModel`.

`TrainerGameModule.makeModel` changes to accept a `TrainerBackendSession`.

`TrainerBackendSession.send` gains an optional reply callback so Core services can decode their own result without routing it through Hades state. Existing game requests remain source-compatible.

The generated `GameModuleDescriptor` gains only save capability flags required for Host presentation. Local save paths and include patterns remain backend-only.

## Save manager UI rewrite

The Hades-specific `Hades2SaveManagerView`, Hades backup state, Hades backup request cases and duplicated save entry points are removed.

The Host exposes one save-management entry when the active module declares support.

The new sheet uses a two-pane management layout:

- left: snapshot inventory, validity state, creation time, file count and live-backup badge;
- right: current save-management capabilities and selected snapshot actions;
- top: pending-restore notice when present;
- primary action: create snapshot;
- selected actions: rename, reveal in Finder, restore, delete;
- restore option: preserve current save as a normal snapshot before restore;
- invalid snapshots remain visible and deletable but cannot be restored.

Restore has one user action. The backend decides whether it can restore immediately, hot-restore, or stage because files are busy. The UI does not ask the user to reason about process/file locking.

When a restore is staged, the sheet reports that current files are busy and the restore will run on target exit. The user can cancel it.

The model owns selection-independent data only. Transient editor state such as rename text and confirmation presentation stays in the View.

## Error handling

Distinct backend errors are required for:

- save management unsupported;
- no real save files found;
- path/manifest unsafe;
- snapshot invalid/corrupt;
- live operation busy;
- staged restore unavailable;
- restore failed but rollback succeeded;
- restore and rollback both failed.

Destructive operations validate IDs and containment before touching disk.

## Testing

All filesystem tests use explicit temporary roots. No test may derive the real user's Hades II save directory.

Required behavior tests cover:

- manifest validation and optional provider containment;
- declarative resolution includes only declared real-save files;
- hot backup retries on racing writes and never commits a partial snapshot;
- snapshot validation rejects extra/missing/corrupt files and symlinks;
- hot-preferred restore runs while the process is alive when files are stable;
- a racing/busy live restore stages rather than mutating when allowed;
- stopped-only policy never mutates while the target runs;
- restore removes only resolved save files and never removes the root;
- rollback restores the pre-transaction bytes;
- failed rollback preserves the recovery copy;
- staged metadata survives backend restart and is applied on explicit target-stop command;
- Core protocol routes save commands without invoking the game adapter;
- a second synthetic game can enable save management without changes to Hades code;
- generic Swift save model decodes snapshot/pending state;
- generic Host contains the save entry and Hades no longer owns save-manager UI logic.

Full Linux checks run before integration. Full macOS/build checks remain target-Mac verification and use the existing real-save-tree sentinel.
