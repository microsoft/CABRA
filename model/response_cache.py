import json
from pathlib import Path


class ResponseCache:
    """
    Tracks which records are already saved in a jsonl file so a 
    run can resume without redoing work, while keeping memory minimal.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._keys: set[tuple[str, str]] = set()

    @staticmethod
    def _key(name: str, dag_id: str) -> tuple[str, str]:
        return (name, dag_id)

    def load(self, retry_errors: bool = False) -> None:
        self._keys.clear()
        if not self.path.exists():
            return
        with self.path.open("r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if retry_errors and not rec.get("output"):
                    continue
                self._keys.add(self._key(rec["name"], rec["dag_id"]))

    def should_skip(self, name: str, dag_id: str) -> bool:
        return self._key(name, dag_id) in self._keys

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(record) + "\n")
        self._keys.add(self._key(record["name"], record["dag_id"]))

    def __len__(self) -> int:
        return len(self._keys)

    def iter_records(self, deduplicate: bool = True):
        """Yield records stored in the jsonl file.

        If deduplicate=True (default), only the last entry for each (name, dag_id)
        is yielded — this handles retried errors correctly.
        """
        if not self.path.exists():
            return
        if not deduplicate:
            with self.path.open("r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    yield json.loads(line)
            return

        records: dict[tuple[str, str], dict] = {}
        order: list[tuple[str, str]] = []
        with self.path.open("r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                key = self._key(rec["name"], rec["dag_id"])
                if key not in records:
                    order.append(key)
                records[key] = rec
        for key in order:
            yield records[key]
