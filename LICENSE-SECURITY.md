# Security notes before public release

This is a functional starting implementation, not a third-party-audited password manager. Before storing real passwords:
1. Review all code and dependencies.
2. Add stronger edge-level rate limiting and abuse protection to public endpoints.
3. Add CSRF protection to the license-generation form.
4. Back up the JSON license store securely and test recovery.
5. Use a persistent filesystem; ephemeral storage loses licenses on restarts/deployments.
6. Run only one service instance/worker: the JSON file lock is process-local and does not coordinate multiple instances.
7. Test clock rollback, expired tickets, corrupted vaults, interrupted writes, and import collision recovery.
8. Build signed platform-specific installers; do not distribute source `main.py` as a finished install.
9. Keep the private signing key out of GitHub and all clients.
10. Treat the local device ID as an identifier, not tamper-proof hardware attestation.
11. Do not claim offline revocation is immediate: a disconnected machine cannot learn about revocations.

CORE KeySafe does not create, require, or authenticate CORE Accounts. No database is used by the license service.
