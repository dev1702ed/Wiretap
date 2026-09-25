"""Dataset identity resolution and dedup. P3.

The failure mode to design against: the same physical table reached via two
connection strings (`localhost` vs `prod-db.internal`, or with/without a port)
resolving to two nodes. That silently fragments the graph and quietly wrecks
the recall number — which is the number the whole project rests on.

TODO(P3): decide whether to canonicalise aggressively (risk: merging genuinely
distinct datasets) or conservatively (risk: fragmentation). Record the decision
and its rationale in docs/ — it is a real tradeoff, not an implementation
detail.
"""


def resolve(namespace: str, name: str) -> str:
    """Return a canonical node key for a dataset."""
    raise NotImplementedError("P3")
