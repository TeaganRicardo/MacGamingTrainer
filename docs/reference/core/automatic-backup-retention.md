# Automatic pre-edit backup retention

Core Save owns this policy (`Backend/core/save_retention.py`), its snapshot
metadata (`save_snapshots.py`), and its confirmed transaction checkpoint
(`save_service.py`). The default count and byte budgets are declared once in
`save_retention.py`; Save Management reads and edits those values through the
Core Save API. A module does not infer backup ownership from game meaning.

## Origin, explicit protection and recovery

New snapshot manifests declare actual creation origin:

- `manual`: an explicit backup request, including an automatically generated
  display name. Manual copies never enter automatic retention.
- `automaticPreEdit`: the verified pre-write snapshot created by a selected
  file replacement. It starts with `retentionEligible=false`.
- `preRestore`: a copy deliberately preserved before whole-set restore. It is
  outside this edit-backup policy.
- `unclassified`: a pre-existing manifest with no origin declaration. It remains
  readable and manageable, and is never inferred to be automatic from its name,
  localized presentation or `automaticName` flag.

A verified successful replacement is the only service checkpoint that marks its
new pre-edit snapshot eligible. Failed/interrupted transactions and a failure to
persist that acknowledgement keep the copy outside automatic eviction, including
after a later successful edit or backend restart. Rollback directories remain
separate recovery evidence and never become snapshot eviction candidates.

Renaming an automatic copy or supplying an explicit name protects it. Save
Management also offers Keep This Backup and, for a successfully committed
automatic copy, an explicit Allow Automatic Cleanup action. Protection does not
change creation origin. Manual, pre-restore and unclassified copies remain
outside retention regardless of naming.

## Cleanup checkpoint and budget

The budget applies to verified, confirmed, unprotected automatic pre-edit copies.
After a successful replacement and verification of the newly created backup,
Core removes the oldest eligible copies until both configured count and logical
byte limits are satisfied. It always keeps the new verified pre-edit recovery
point, even if that single copy exceeds the byte budget. Pending restore inputs
are pinned. An indeterminate staged restore or a retained rollback directory
pauses the automatic sweep until recovery is resolved.

Saving a policy does not itself delete anything. Listing, launching the app,
manually creating a backup, renaming/protecting a backup and ordinary restores
do not trigger eviction. There is no periodic cleanup or automatic retry.
Invalid policy data pauses deletion rather than silently applying defaults.

Retention runs after the save transaction has committed, verified and completed
its rollback cleanup. A maintenance error returns separate retention feedback;
it cannot turn successful Apply into failure, rerun the edit, or roll back the
installed bytes. Save Management shows the remaining copies and warning. The
next successful edit may perform another single sweep.

## Storage reporting

Inventory bytes are measured from actual contained directory entries, including
manifest and extra/invalid files. They are logical file bytes, excluding directory
and filesystem allocation/compression overhead; symbolic links are not followed.
Snapshot and recovery counts/bytes are reported separately. A size that cannot
be read is explicitly unknown; displayed totals then contain only known bytes.
Unknown eligible-copy sizes pause eviction. Protected and unclassified storage
remains visible and may exceed the automatic budget.

Core protocol commands are `core.save.set_retention` (`maxCount`, `maxBytes`)
and `core.save.protect` (`snapshotId`, boolean `protected`). The existing inventory
returns `retention`, `storageUsage` and each snapshot's origin/protection/size.
The policy sheet preserves a focused draft during background observations and
refreshes unfocused fields. Its own acknowledged save owns field disabling;
generic inventory refresh does not interrupt editing. The native control fixture
exercises Return/blur, explicit Save acknowledgement and feedback, and both
protection menu actions through the real Core service and temporary save roots.
Visual acceptance, real saves, game reload and later game-authored save behavior
remain user-run.
