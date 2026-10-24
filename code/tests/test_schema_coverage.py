"""Ensure participant-visible evidence schema remains covered."""

from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

from ghostdata.coverage import unsupported_schema_items


class TestSchemaCoverage(unittest.TestCase):
    def test_dataset_schema_has_no_uncovered_collections_or_tables(self):
        root = Path(__file__).resolve().parents[2]
        collections: set[str] = set()
        service_blocks: set[str] = set()
        for path in (root / "dataset" / "evidence" / "records").glob("*.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("collection"):
                collections.add(document["collection"])
            for snapshot in document.get("snapshots", []):
                if snapshot.get("collection"):
                    collections.add(snapshot["collection"])
            for service, blocks in document.get("service_exports", {}).items():
                service_blocks.update(f"{service}/{block}" for block in blocks)

        sql_tables: set[str] = set()
        for path in (root / "dataset" / "evidence" / "databases").glob("*.sql"):
            connection = sqlite3.connect(":memory:")
            try:
                connection.executescript(path.read_text(encoding="utf-8", errors="replace"))
                sql_tables.update(
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                )
            finally:
                connection.close()

        unsupported = unsupported_schema_items(collections, service_blocks, sql_tables)
        self.assertEqual(unsupported, {
            "collections": set(),
            "service_blocks": set(),
            "sql_tables": set(),
        })
