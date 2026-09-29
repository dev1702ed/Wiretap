# Decision: dataset identity is resolved conservatively

Status: decided in P3. Code: `backend/app/identity.py`.

## The question

A dataset's graph node is its `(namespace, name)` pair. The backend has to decide
when two pairs mean the same physical dataset. It can go wrong in two ways:

- **Fragmentation.** One table, reached through two connection strings
  (`postgres://localhost:5432` and `postgres://prod-db.internal:5432`), becomes
  two nodes. The edges on each side are real, but the chain between them breaks,
  so **recall** drops.
- **False merge.** Two different tables that happen to share a spelling become
  one node, and the graph shows lineage that never happened. **Precision** drops.

## The decision

`resolve(namespace, name)` applies only **deterministic, lossless** normalisation:

| Applied | Why it is lossless |
|---|---|
| Strip surrounding whitespace from namespace and name | Never part of a real identifier |
| Lowercase the URI scheme (`POSTGRES://` → `postgres://`) | Schemes are case-insensitive (RFC 3986 §3.1) |
| Lowercase the host (`Prod-DB` → `prod-db`) | Host names are case-insensitive (RFC 3986 §3.2.2) |

Nothing else changes. Specifically, we do **not**:

- **Resolve DNS**, or merge a host name with an IP address. The answer depends on
  when and where the lookup runs, so replaying the event log could build a
  different graph. The graph must be rebuildable from the log exactly.
- **Canonicalise `localhost`** (or `127.0.0.1`). It means the machine that
  emitted the event. `postgres://localhost:5432` from two hosts is two databases.
  Merging them would be the textbook false merge.
- **Merge hosts, add default ports, or drop ports.** `prod-db` and
  `prod-db.internal` may well be the same server, but nothing in the event says so.
- **Change the name's case.** Postgres folds unquoted identifiers to lower case
  but keeps quoted ones as written, and Kafka topics are case-sensitive.
  Lowercasing names would merge datasets that really are different.

The ground-truth namespaces (`postgres://localhost:5432`, `kafka://localhost:9092`)
come through unchanged.

## The trade-off, stated plainly

For this instrument, a false merge is worse than fragmentation.

- A false merge makes up an edge. Once it is in the graph, no later step can tell
  it from an attested edge. It inflates the lineage DCP reports and corrupts the
  precision number the project exists to produce.
- Fragmentation loses an edge, but it fails visibly. It shows up as a missing
  node or edge in a ground-truth score, so recall reports it honestly instead of
  hiding it.

The price: if a deployment reaches one database through several host names, its
graph will fragment, and recall will be lower than capture alone would give.
The fix is on the emitting side. Configure clients with the same connection
host, or add an explicit, reviewable alias table later, where every merge is a
recorded assertion rather than a guess. Neither exists in v1.

## Follow-ups (not built)

- An explicit alias map (`prod-db.internal:5432` ≡ `10.0.0.5:5432`), declared by
  an operator and applied at resolution time. Every merge would be listed.
- Kafka cluster ID as namespace (spec decision #3's alternative). It would stop
  clients that list different brokers of one cluster from fragmenting.
