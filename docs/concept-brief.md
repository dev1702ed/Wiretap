# DCP: Data Connectivity Protocol — Concept Brief

*Solving data lineage at the transport layer*

## 1. The core thesis

Data lineage is currently solved as an application-layer problem. Every lineage system in
production today — OpenLineage, Marquez, DataHub, Atlas, dbt's DAG, Spark listeners — works by
instrumenting the tools that move data. You write a Spark listener, an Airflow plugin, a SQL
parser. Lineage is declared by the application about itself, and inferred from application
semantics.

DCP inverts this. The observation is simple: no data moves without crossing a wire. A JDBC
connection, a gRPC call, an HTTP request, a Kafka produce — every act of data movement is a
transport event before it is an application event. So lineage should be captured where the
movement physically happens: at the RPC and session boundary, via interceptors, middleware, and
connection shims, with a provenance context propagated in protocol metadata across hops.

Lineage stops being a thing applications report and becomes a thing the network observes. This
is the same move the service mesh made for observability and mTLS: take a concern that every
application was reimplementing badly and push it down the stack until it becomes universal and
application-transparent.

## 2. What it aims to achieve

- **Coverage by default.** Any system speaking an instrumented protocol is covered without
  touching its code. This kills the N-frameworks × M-tools integration explosion, and closes the
  dark zones — ad-hoc scripts, notebooks, internal microservices — that framework-specific
  instrumentation never reaches.
- **Attested rather than declared lineage.** Provenance derived from bytes actually on the wire,
  not from a scheduler's stated intent. An edge exists because a transfer was observed, which is
  a materially stronger claim for audit and compliance.
- **Multi-hop provenance propagation.** A lineage context ID carried in protocol metadata that
  survives hops — conceptually W3C Trace Context, but for data provenance instead of request
  causality. This reconstructs true multi-hop DAGs instead of correlating disconnected events
  after the fact.
- **Real-time graph.** Lineage as a live stream, not a nightly reconstruction.
- **Enforcement, not just recording.** Because the interceptor sits inline, it can block a
  transfer, not merely log it — residency violations, PII crossing a trust boundary,
  unauthorized sink writes.
- **Downstream capabilities unlocked:** blast-radius and impact analysis, PII propagation
  tracking, GDPR/DPDP attestation, and incident forensics.

**The central tension, named up front:** the transport layer sees endpoints and bytes, not
meaning. Coarse lineage (service A → table B) is nearly free. Column-level lineage requires
payload introspection, which costs latency and creates its own privacy surface. How much semantic
granularity is recoverable at what overhead is the research problem — not a detail to hand-wave.

## 3. Requirements brief for a research model

### Context
I am designing DCP (Data Connectivity Protocol), a transport-layer data lineage system. Instead
of application-layer instrumentation (OpenLineage, Spark listeners, SQL parsing), DCP intercepts
at the RPC and session boundary — gRPC interceptors, JDBC/DBAPI wrappers, HTTP middleware, Kafka
client hooks — and propagates a provenance context through protocol metadata across hops.
Lineage is emitted as a byproduct of communication. Evaluate feasibility and specify what a
credible prototype must satisfy.

### A. Positioning and prior art
Survey and differentiate against: OpenLineage/Marquez, DataHub, Apache Atlas, Egeria, Spline,
Monte Carlo; eBPF-based network observability (Pixie, Cilium Hubble); service mesh telemetry
(Istio, Linkerd); OpenTelemetry's trace-context propagation and any existing data-provenance
extensions; and database-native provenance research (Trio, PROV-DM, why/where-provenance
literature). Identify precisely what is genuinely unclaimed and what is a reframing of existing
work.

### B. Interception surface
Which protocols must be covered for a defensible minimum viable claim of universality? Compare
three deployment models — in-process library interceptor, sidecar proxy, and eBPF kernel-level —
on coverage, language-agnosticism, operational burden, and whether each can see enough to
identify the dataset rather than just the endpoint.

### C. Metadata and propagation model
Specify the provenance envelope: fields, identity scheme for datasets and jobs, and how context
propagates through gRPC metadata, HTTP headers, Kafka record headers, and JDBC connection
properties. Address protocols with no metadata channel. Define compatibility with PROV-DM and
OpenLineage's schema — interoperate rather than compete.

### D. Granularity ladder
Formalize achievable levels: endpoint-to-endpoint, dataset-to-dataset, table-level, and
column-level. For each, state what must be inspected, the inference technique (schema
negotiation, query-text capture, statistical payload sampling), and the accuracy, latency, and
privacy cost. Determine whether column-level lineage is reachable without full payload capture.

### E. Hard cases
Analyze and propose handling for: asynchronous decoupling (Kafka severs synchronous causality —
this is the hardest case), batching and fan-in aggregation where N inputs produce one output,
end-to-end encrypted payloads, transfers crossing into third-party SaaS, transitive movement
through intermediate caches, and context loss at unenlightened hops. State clearly which are
unsolvable at this layer.

### F. Performance budget
Propose defensible targets for p50/p99 added latency and throughput degradation, memory footprint
per intercepted connection, and emission volume at scale. Specify sampling strategies that
preserve graph completeness — note that uniform sampling breaks lineage in a way it does not
break tracing, since a dropped edge disconnects the graph.

### G. Graph construction
Streaming edge ingestion, dataset identity resolution and deduplication, temporal versioning
(lineage is time-varying), and cycle handling. Recommend storage: property graph vs. relational
vs. purpose-built. Note that a prototype may use networkx in-memory; specify what breaks at what
scale.

### H. Evaluation methodology
This is the section I most need rigor on. Propose: a testbed with known ground-truth lineage;
precision and recall metrics for edge and node recovery; benchmarks against OpenLineage on
identical workloads; an adversarial suite of data movements that application-layer
instrumentation provably misses; and an overhead measurement protocol. Define what result would
constitute a genuine finding versus a demo.

### I. Threat and trust model
Who can forge or suppress a provenance context? What guarantees hold if a participating service
is malicious? Does inline enforcement introduce a new availability failure mode?

### J. Falsification
State the strongest arguments that this approach is wrong — cases where transport-layer capture
is fundamentally insufficient, or where the semantic gap makes output too coarse to be useful. If
the idea should be narrowed in scope to survive, say what the narrowed version is.

### Deliverable
A feasibility assessment, a prioritized requirements list separating must-have from
research-open, and a recommended prototype scope demonstrating the core claim with the least
engineering surface.

*Section J is what makes this land. A project that names its own failure conditions reads as
research; one that does not reads as a pitch.*
