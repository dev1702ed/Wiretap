# Vendored OpenLineage schema

`OpenLineage.json` is the official OpenLineage JSON Schema, copied byte for byte so
the bridge's tests can validate its output offline.

| | |
|---|---|
| Source | <https://raw.githubusercontent.com/OpenLineage/OpenLineage/1.53.0/spec/OpenLineage.json> |
| Release tag | `1.53.0` of <https://github.com/OpenLineage/OpenLineage> |
| Spec version (`$id`) | `https://openlineage.io/spec/2-0-2/OpenLineage.json` |
| SHA-256 | `69f68bee00b9beac88a87059c0102410e7bb05f3f43c46d02a0409831eceb0d2` |
| Licence | Apache License 2.0, © The OpenLineage project authors (<https://github.com/OpenLineage/OpenLineage/blob/1.53.0/LICENSE>) |

Do not edit it. To upgrade, replace the file with the one from a newer release tag,
update this table, and update `OPENLINEAGE_SCHEMA_URL` in `dcp_openlineage/__init__.py`
to the new `$id`; `tests/test_bridge_schema.py` checks the two agree.
