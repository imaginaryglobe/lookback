"""Thread-safe log relay from the indexer's background thread to SSE clients in main.py.

The indexer runs in a separate OS thread (started by POST /index/start). Log lines
produced there need to reach any number of browser tabs subscribed to the SSE
stream at /index/progress. A logging.Handler pushes formatted lines into a
process-wide queue per subscriber, plus a ring buffer so a newly-opened SSE
connection can replay recent history instead of starting blank.
"""
import logging
import queue
import threading
from collections import deque

_lock = threading.Lock()
_subscribers = []
_history = deque(maxlen=200)


def broadcast(line: str) -> None:
    with _lock:
        _history.append(line)
        for q in _subscribers:
            q.put_nowait(line)


def subscribe() -> "queue.Queue[str]":
    q = queue.Queue()
    with _lock:
        for line in _history:
            q.put_nowait(line)
        _subscribers.append(q)
    return q


def unsubscribe(q: "queue.Queue[str]") -> None:
    with _lock:
        if q in _subscribers:
            _subscribers.remove(q)


class BroadcastHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        broadcast(self.format(record))


def get_indexer_logger() -> logging.Logger:
    logger = logging.getLogger("indexer")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)

        broadcast_handler = BroadcastHandler()
        broadcast_handler.setFormatter(fmt)
        logger.addHandler(broadcast_handler)

        logger.propagate = False
    return logger
