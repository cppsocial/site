from datetime import UTC, datetime
from pathlib import Path

from schemas.blocks import Provenance as ProvenanceSchema

from .dataset import YamlDataset

class Provenance:
    def __init__(self, output_path: Path):
        self.source_urls: list[str] = []
        self.path = output_path
        self.dataset: YamlDataset = YamlDataset(
            output_path,
            ProvenanceSchema,
            "meta-updater"
        )

        if output_path.exists():
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

provenance_tracker : Provenance | None = None

def start_provenance_tracking(path: Path):
    global provenance_tracker
    provenance_tracker = Provenance(path)

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
    if provenance_tracker is not None:
        provenance_tracker.add_source_url(url)
    else:
        print(
            "Warning: provenance_tracker is not initialized. "
            "Call Provenance(path) before tracking provenance."
        )
