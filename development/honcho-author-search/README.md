# Minimal external Honcho correction: development evidence

**Not a deployment, core patch, release tag or approval to adopt.**

- Vanilla Hermes core: `e5f2b15300a3d04978e4c07cc64adc7bcf8e7b1c`.
- Official catalogue source: `plastic-labs/honcho@e2d2aba182862deeb846e5cd4a30a41bce0ed82a`, subdirectory `hermes-plugin-honcho`, manifest version `1.0.0`.
- Local correction: `honcho-author-search.patch`, SHA256 `1645678fa10ae90c941a15c448978656574543862b485758376aba4b3f01acbf`.
- Tested external Python SDK: `honcho-ai==2.2.0`.

## Scope

Three external-plugin files only. Use the documented workspace-search `peer_id` **author** filter, remove the peer-creation fallback, propagate backend errors through the existing tool error handler, and describe the same semantics in both schema copies. Preserve existing auth-refresh handling. No Hermes core implementation is changed.

User searches find messages authored by the user; `ai` finds the current assistant; an explicit peer finds that author. Search both sides when both are required. This is not perspective search and is not an access-control boundary. Workspace initialisation still uses the SDK's get-or-create request: removing the peer fallback does not make the whole SDK read-only.

## Evidence and reproduction boundaries

The tests use the authorised local rehearsal paths documented inside them. This is a bounded deployment-evidence branch, not an upstream-ready generic test package. Run in a network-isolated container with only development source and authorised copies mounted; never run them in a production environment.

- `test_honcho_candidate.py`: real SDK request/filter assertions, auth rejection and refreshed-client retry, failed-search errors, plus explicitly opt-in restored-history HTTP checks. `HERMES_RESTORED_TEST=1` is permitted only in the isolated restored database/API namespace; the private fixture file is deliberately not published.
- `test_provider_loading.py`: external-provider discovery and copied-configuration resolution. Requires private authorised copies; no production API calls.
- `test_telegram_sdk.py`: pinned Telegram SDK initialisation, dispatch and shutdown through an in-memory transport. No Telegram messages or polling.

The final combined invocation is `python -m pytest -q -p no:cacheprovider test_honcho_candidate.py test_provider_loading.py test_telegram_sdk.py` with the restored-test opt-in only inside the isolated namespace. Earlier `provider.log` totals included other selected tests; they must not be attributed to the two provider-loading cases alone.

Restored searches replay retained database vectors through the unchanged production server's real HTTP/filter/retrieval path. They do **not** prove fresh embedding generation, ranking quality, complete recall, live authentication, or production server compatibility after an upgrade. No Honcho server upgrade is included.

Independent review approved the exact plugin patch for this development-only publication. Private configuration, databases, source messages, vectors, tokens and raw traces are excluded. Production adoption, residual profile-isolation risk acceptance and live smoke tests remain separate decisions.
