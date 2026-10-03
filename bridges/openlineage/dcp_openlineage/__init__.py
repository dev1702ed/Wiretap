"""DCP -> OpenLineage batch bridge. P4.

Translates recorded DCP events into OpenLineage RunEvents, so DCP's lineage
lands in the catalogs people already run (Marquez, DataHub) instead of
replacing them. Stdlib only.
"""

__version__ = "0.1.0.dev0"

# The vendored spec's $id (schema/OpenLineage.json, release tag 1.53.0).
OPENLINEAGE_SCHEMA_URL = "https://openlineage.io/spec/2-0-2/OpenLineage.json"
RUN_EVENT_SCHEMA_URL = f"{OPENLINEAGE_SCHEMA_URL}#/$defs/RunEvent"

_REPO = "https://github.com/dev1702ed/Wiretap"
PRODUCER_URI = f"{_REPO}/tree/main/bridges/openlineage"
DCP_FACET_SCHEMA_URL = f"{_REPO}/blob/main/bridges/openlineage/facets/DcpRunFacet.json"
