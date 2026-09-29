"""Dataset identity resolution. P3.

The failure mode to design against: the same physical table reached via two
connection strings (`localhost` vs `prod-db.internal`, or with/without a port)
resolving to two nodes. That silently fragments the graph and quietly wrecks
the recall number — which is the number the whole project rests on.

The opposite failure is worse for this instrument: merging two distinct
datasets into one node invents lineage that never happened, and a false edge
corrupts precision in a way no later step can detect. So resolution here is
conservative: deterministic, lossless normalisation only. No DNS, no host
aliasing, and `localhost` is left alone — it is relative to the machine that
emitted the event. Rationale and trade-off: docs/decisions/identity.md.
"""

import re


def resolve(namespace: str, name: str) -> tuple[str, str]:
    """Return the canonical (namespace, name) key for a dataset.

    Strips surrounding whitespace from both parts and lowercases the scheme
    and host of the namespace, which are case-insensitive by definition.
    Everything else (userinfo, port, path, the name itself) is kept exactly:
    Postgres quoted identifiers and Kafka topics are case-sensitive.
    """
    return _namespace(namespace.strip()), name.strip()


# scheme://authority, then anything from the first / ? or # onwards (RFC 3986).
_URI_RE = re.compile(
    r"^(?P<scheme>[^:/?#]+)://(?P<authority>[^/?#]*)(?P<rest>.*)$", re.DOTALL
)


def _namespace(namespace: str) -> str:
    match = _URI_RE.match(namespace)
    if match is None:
        return namespace
    userinfo, at, hostport = match["authority"].rpartition("@")
    return (
        f"{match['scheme'].lower()}://{userinfo}{at}{hostport.lower()}{match['rest']}"
    )
