"""Console emitter. P1. The first-look sink and the debugging workhorse."""

import json

from dcp.emitters.base import Emitter


class ConsoleEmitter(Emitter):
    def emit(self, event) -> None:
        print(json.dumps(event.to_dict()))

    def flush(self, timeout: float = 5.0) -> None:
        return None