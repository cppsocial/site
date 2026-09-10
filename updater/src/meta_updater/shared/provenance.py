from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from schemas.blocks import Provenance as ProvenanceSchema

from .dataset import YamlDataset


class Provenance:
    def __init__(self, output_path: Path, *, retain_existing: bool = True):
        self.source_urls: list[str] = []
        self.path = output_path
        self.dataset: YamlDataset = YamlDataset(
            output_path,
            ProvenanceSchema,
            "meta-updater"
        )

        if retain_existing and output_path.exists():
            provenance = self.dataset.load()
            self.source_urls = provenance.source_urls

    def add_source_url(self, url: str):
        self.source_urls.append(url)

    def finish(self):
        provenance = ProvenanceSchema(
            retrieved_at=datetime.now(UTC).date().isoformat(),
            source_urls=list(dict.fromkeys(self.source_urls))
        )
        self.dataset.update(provenance, check=False)


provenance_tracker: Provenance | None = None
provenance_suppressed = 0


def start_provenance_tracking(path: Path, *, retain_existing: bool = True):
    global provenance_tracker
    provenance_tracker = Provenance(path, retain_existing=retain_existing)


def finish_provenance_tracking():
    global provenance_tracker
    if provenance_tracker is not None:
        provenance_tracker.finish()
        provenance_tracker = None


def cancel_provenance_tracking():
    global provenance_tracker
    provenance_tracker = None


def track_provenance(url: str):
    global provenance_tracker
    if provenance_suppressed:
        return
    if provenance_tracker is not None:
        provenance_tracker.add_source_url(url)
    else:
        print(
            "Warning: provenance_tracker is not initialized. "
            "Call Provenance(path) before tracking provenance."
        )


def retain_provenance_urls(urls: set[str]):
    """Drop tracked URLs that do not back any retained output content."""
    if provenance_tracker is not None:
        allowed = {url.rstrip("/") for url in urls}
        provenance_tracker.source_urls = [
            url
            for url in provenance_tracker.source_urls
            if url.rstrip("/") in allowed
        ]


@contextmanager
def provenance_transaction():
    """Only retain URLs tracked while a derived content record is accepted."""
    tracker = provenance_tracker
    checkpoint = len(tracker.source_urls) if tracker is not None else 0
    try:
        yield
    except Exception:
        if tracker is not None:
            del tracker.source_urls[checkpoint:]
        raise


@contextmanager
def suppress_provenance():
    """Suppress tracking for discovery requests that do not supply content."""
    global provenance_suppressed
    provenance_suppressed += 1
    try:
        yield
    finally:
        provenance_suppressed -= 1
