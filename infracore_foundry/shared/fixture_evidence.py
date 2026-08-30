"""Read-only access to registered synthetic source rows, never arbitrary files."""
import csv
import hashlib
import io
import re

from shared.fixture_operation import CLIENT_ID, FIXTURE_ID, SOURCE_ID, authorize_fixture, _DIGESTS


def read_fixture_evidence(record_id: str, client_id: str) -> dict:
    if client_id != CLIENT_ID:
        raise PermissionError("Evidence is restricted to the synthetic fixture tenant")
    if not isinstance(record_id, str) or not re.fullmatch(r"[CDAR]ROW-[0-9]{3}", record_id):
        raise LookupError("Unknown fixture record")
    approved = authorize_fixture({"fixture_id": FIXTURE_ID})
    for path in approved.paths:
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != _DIGESTS[path.name]:
            raise PermissionError("Fixture evidence checksum mismatch")
        for number, row in enumerate(csv.DictReader(io.StringIO(content.decode("utf-8"))), 1):
            if row.get("source_record_id") == record_id:
                return {
                    "recordId": record_id, "fixtureId": FIXTURE_ID,
                    "sourceId": SOURCE_ID, "filename": path.name,
                    "dataRow": number, "fileSha256": digest,
                    "batchId": approved.batch_id, "synthetic": True,
                    "source": "sealed-local-fixture", "fields": row,
                }
    raise LookupError("Unknown fixture record")
