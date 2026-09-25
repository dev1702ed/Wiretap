"""Interceptors — where DCP actually sees the wire.

Each interceptor wraps a client library's session boundary, reads the control
path (query text, topic, connection params), and emits an event. None of them
touch result payloads — that is what keeps overhead in the sub-millisecond
range and keeps DCP out of the privacy surface entirely.
"""
