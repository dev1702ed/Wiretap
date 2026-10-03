"""POST OpenLineage events to a lineage API such as Marquez. P4.

This is a batch tool, not DCP's monitor-only capture path: it fails loudly.
Each event goes to `{url}/api/v1/lineage` as a JSON body, one request per
event, in order. Network errors and 5xx responses (and 408/429) are retried
with exponential backoff; any other 4xx, or running out of retries, raises
TransportError and stops the batch.
"""

import http.client
import json
import time
import urllib.error
import urllib.request

LINEAGE_PATH = "/api/v1/lineage"
_RETRYABLE_4XX = frozenset({408, 429})


class TransportError(RuntimeError):
    """An event could not be delivered. Nothing after it was sent."""


def post_events(
    url: str,
    events: list[dict],
    *,
    max_retries: int = 3,
    backoff: float = 0.5,
    timeout: float = 10.0,
    sleep=time.sleep,
) -> int:
    """Send every event, in order. Returns the number sent."""
    endpoint = url.rstrip("/") + LINEAGE_PATH
    opener = urllib.request.build_opener()
    for index, event in enumerate(events):
        _post_one(opener, endpoint, event, index, max_retries, backoff, timeout, sleep)
    return len(events)


def _post_one(opener, endpoint, event, index, max_retries, backoff, timeout, sleep) -> None:
    body = json.dumps(event).encode("utf-8")
    reason = "not sent"
    for attempt in range(max_retries + 1):
        if attempt:
            sleep(backoff * 2 ** (attempt - 1))
        request = urllib.request.Request(
            endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            exc.close()
            reason = f"HTTP {exc.code}: {detail}"
            if 400 <= exc.code < 500 and exc.code not in _RETRYABLE_4XX:
                break
        except (OSError, http.client.HTTPException) as exc:
            reason = repr(exc)
        else:
            return
    raise TransportError(f"event {index} was not delivered to {endpoint}: {reason}")
