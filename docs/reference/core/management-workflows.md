# Shared management workflows

`TrainerProfileManagerView` owns feature-profile sheet interaction for both
production modules: name draft, stored selection, refresh, save/load/delete,
busy admission, feedback and dismissal. Modules supply display strings, neutral
name/date entries, current availability and commands. Profile contents, storage,
migration, replay and shortcut compatibility stay in their original game owners.

`TrainerProfileSelection` keeps the editable name separate from the selected
stored profile. A save requests selection of its name; an acknowledged inventory
must contain that name before it can become a load/delete target. Failure keeps
the previous stored selection and name draft. Deletion/refresh reconciles to an
existing entry or clears selection for an empty inventory. Closing the sheet
does not cancel or replay an in-flight module command. Hades II clears its
sheet-specific shortcut compatibility warning when the sheet disappears.

Portable selection regressions cover creation, failed save, external inventory
changes and empty-state reconciliation. The existing Hades I and II native
frontend fixtures drive the same shared sheet through their real module
adapters, including name edits, save/load/delete, backend failure feedback,
shortcut compatibility and dismissal. These fixtures use temporary synthetic
backends and do not establish actual game acceptance.
