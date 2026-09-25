# OpenLineage bridge (P4)

Translates DCP events into OpenLineage RunEvents so the graph renders in Marquez and
DataHub with no extra work.

Design note: DCP's dataset identity model is deliberately identical to OpenLineage's
(`namespace` + `name`), so translation is mechanical rather than lossy.

**Positioning:** DCP feeds your existing catalog. It does not replace it. Lead every doc
with that — it removes the rip-and-replace objection, which is the first one anyone raises.

The mapping that needs care: DCP has no notion of a "run" in the OpenLineage sense. A
long-lived script producing events over hours is not a bounded run. TODO(P4): decide
whether to synthesise run boundaries or map each trace to a run. Leaning trace→run.
