# Versioning

MacGamingTrainer uses one product version and one monotonically increasing build number.

- Current product version: 0.1
- Current build: 1
- Development state is represented by Git branches and commits, not dev-number suffixes.
- main is the canonical working baseline.
- Product tags are reserved for deliberately captured deliverable snapshots, for example v0.1.
- Host protocol, module protocol, persistence schema, profile schema and Lua source revision are compatibility/internal revision numbers. They are independent of the product version and are not reset with product versioning.
