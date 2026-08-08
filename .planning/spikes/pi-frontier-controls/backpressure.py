"""Spike 007: stable-key coalescing and bounded concurrent admission."""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Work:
    key: str
    domain: str
    delay: float = 0.002


class FairScheduler:
    def __init__(self, workers: int = 2, max_queue: int = 4):
        self.queue: queue.Queue[Work | None] = queue.Queue(maxsize=max_queue)
        self.seen: set[str] = set()
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.accepted: list[str] = []
        self.rejected: list[str] = []
        self.completed: list[str] = []
        self.thread_list = [threading.Thread(target=self._worker, daemon=True) for _ in range(workers)]

    def start(self) -> None:
        for thread in self.thread_list:
            thread.start()

    def submit(self, work: Work) -> str:
        with self.lock:
            if work.key in self.seen:
                self.rejected.append(f"duplicate:{work.key}")
                return "duplicate"
            self.seen.add(work.key)
        try:
            self.queue.put_nowait(work)
        except queue.Full:
            self.rejected.append(f"backpressure:{work.key}")
            return "backpressure"
        self.accepted.append(work.key)
        return "accepted"

    def close(self) -> None:
        self.queue.join()
        for _ in self.thread_list:
            self.queue.put(None)
        for thread in self.thread_list:
            thread.join()

    def _worker(self) -> None:
        while True:
            work = self.queue.get()
            if work is None:
                self.queue.task_done()
                return
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(work.delay)
            with self.lock:
                self.completed.append(work.key)
                self.active -= 1
            self.queue.task_done()


def main() -> None:
    scheduler = FairScheduler(workers=2, max_queue=4)
    scheduler.start()
    outcomes = [scheduler.submit(work) for work in [
        Work("A-1", "A"), Work("B-1", "B"), Work("A-1", "A"), Work("C-1", "C"), Work("D-1", "D"), Work("E-1", "E"),
    ]]
    scheduler.close()
    report = {
        "outcomes": outcomes,
        "accepted": scheduler.accepted,
        "rejected": scheduler.rejected,
        "completed": scheduler.completed,
        "max_active": scheduler.max_active,
        "queue_limit": 4,
        "duplicate_keys": [item for item in scheduler.rejected if item.startswith("duplicate:")],
        "authority_unchanged": True,
    }
    assert report["max_active"] <= 2
    assert report["duplicate_keys"] == ["duplicate:A-1"]
    assert len(set(report["completed"])) == len(report["completed"])
    assert {"A-1", "B-1", "C-1", "D-1"}.issubset(report["completed"])
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
