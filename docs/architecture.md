        # Architecture

        Vaultix uses a three-repository public architecture.

        Current staged focus: `2026-02` - Security and disclaimer pass.

        - `vaultix-web` owns the public landing page and static app shell.
- `vaultix-data` owns the reference Aave data snapshot pipeline.
- `vaultix-docs` owns history, architecture, and operating guidance.
- The split is intentional: no Nomexis contract/oracle/web monorepo inheritance.
- Privacy assumptions are documented separately so public copy and internal control language do not drift.
- Testing and optimization notes live here so the website repo remains static and publishable.
