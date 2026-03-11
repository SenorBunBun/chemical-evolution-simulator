class IdGen:
    """Simple incrementing ID generator. Globally unique across all entity types."""

    def __init__(self):
        self._next = 0

    def next(self) -> int:
        val = self._next
        self._next += 1
        return val
