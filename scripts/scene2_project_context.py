"""Anonymous, session-scoped Resolve context signal for the MCU worker."""
import os
from pathlib import Path
import re
import time

CONTEXT_PATH = Path.home() / "Library/Caches/nk-scene2-project-context.csv"
MAX_AGE_MS = 1500
ID_PATTERN = re.compile(r"[0-9a-f]{16}\Z")


def context_identity(app):
    try:
        project = app.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline() if project else None
        if timeline:
            ids = project.GetUniqueId(), timeline.GetUniqueId()
            if all(isinstance(v, str) and v for v in ids):
                return ids
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass
    return None


def parse_context(row, run_id, now_ms):
    if not ID_PATTERN.fullmatch(run_id or ""):
        return None
    parts = row.strip().split(",")
    if len(parts) != 4:
        return None
    stamp, source, generation, available = parts
    if source != run_id or not generation.isdecimal() or available not in ("0", "1"):
        return None
    try:
        stamp, generation = int(stamp), int(generation)
    except ValueError:
        return None
    if generation <= 0 or not 0 <= now_ms - stamp <= MAX_AGE_MS:
        return None
    return generation, available == "1"


def read_context(path, run_id, now_ms):
    try:
        with path.open("r", encoding="ascii") as stream:
            line = stream.read(128)
        if len(line) >= 128:
            return None
        return parse_context(line, run_id, now_ms)
    except (OSError, UnicodeError):
        return None


class ContextPublisher:
    def __init__(self, run_id, path=CONTEXT_PATH, wall=time.time):
        if not ID_PATTERN.fullmatch(run_id or ""):
            raise ValueError("invalid Scene 2 session ID")
        self.run_id, self.path, self.wall = run_id, path, wall
        self.identity, self.generation = None, 0

    def publish(self, identity):
        if self.generation == 0 or identity != self.identity:
            self.generation += 1
            self.identity = identity
        line = "%d,%s,%d,%d\n" % (
            round(self.wall() * 1000), self.run_id, self.generation,
            int(identity is not None))
        temp = self.path.with_name(self.path.name + ".tmp-%d" % os.getpid())
        try:
            temp.write_text(line, encoding="ascii")
            os.replace(temp, self.path)
        finally:
            if temp.exists():
                temp.unlink()
        return self.generation, identity is not None


class ContextGate:
    def __init__(self, run_id, path=CONTEXT_PATH):
        if not ID_PATTERN.fullmatch(run_id or ""):
            raise ValueError("invalid Scene 2 session ID")
        self.run_id, self.path = run_id, path
        self.generation = None
        self.ready = False

    def check(self, mixer, now_ms):
        state = read_context(self.path, self.run_id, now_ms)
        if state is None:
            if self.ready:
                mixer.rearm(invalidate_host=True)
            self.ready = False
            return False
        generation, available = state
        if self.generation is None:
            self.generation = generation
        else:
            if generation != self.generation or (not available and self.ready):
                mixer.rearm(invalidate_host=True)
            self.generation = generation
        self.ready = available
        return self.ready
