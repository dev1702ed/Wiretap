# Concepts

## The thesis

No data moves without crossing a wire. Every transfer is a transport event before it is an
application event. So capture it at the session boundary, and let lineage be a byproduct of
communication rather than something applications are trusted to report about themselves.

## Declared vs. attested lineage

Application-layer lineage is *declared*: a scheduler states its intent, and a plugin reports
what it believes happened. DCP's edges are *attested*: an edge exists because a transfer was
observed. That is a materially stronger claim for audit — and a weaker one for semantics,
since the transport layer sees endpoints and bytes, not meaning.

## The central tension, named up front

Coarse lineage (service A → table B) is nearly free at this layer. Column-level lineage
requires payload introspection, which costs latency and creates a privacy surface DCP
otherwise avoids entirely. How much semantic granularity is recoverable at what overhead is
the open research question — not a detail to wave through.

v1 answers it by refusing the question: table-level only, column *names* where they come free
from the result schema, no payload inspection at all.

## Why this is not a service mesh

A mesh sees requests. DCP needs to see *datasets* — which table, which topic. That requires
reading the control path (query text, topic names), which is above where a mesh operates and
below where a framework plugin sits. The gap between those two is the space this occupies.

## Prior art worth reading before contributing

- OpenLineage / Marquez — the application-layer standard DCP feeds rather than replaces
- Pixie's eBPF protocol tracer — socket-level protocol parsing, already productised; read
  this before proposing an eBPF deployment model
- W3C Trace Context — the propagation model DCP borrows wholesale for provenance
- Buneman, Khanna & Tan, "Why and Where" (ICDT 2001) — the vocabulary the granularity
  ladder should be speaking
