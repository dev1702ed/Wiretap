"""Carrying provenance context across hops.

One idea, two encodings: put the context where the protocol already has room
for it. Postgres has no metadata channel, so the context rides inside a SQL
comment. Kafka has real headers, so it rides there.

Both implement the same inject/extract shape, deliberately mirroring
OpenTelemetry's propagator interface.
"""
