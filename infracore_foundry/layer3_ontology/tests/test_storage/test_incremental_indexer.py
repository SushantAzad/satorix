import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from storage.incremental_indexer import IncrementalIndexer


class TestIncrementalIndexer:
    def setup_method(self):
        self.indexer = IncrementalIndexer()

    def test_same_data_produces_same_hash(self):
        data = {"cin": "L45201MH2003PLC142301", "name": "Test Co", "status": "Active"}
        h1 = self.indexer.compute_hash(data)
        h2 = self.indexer.compute_hash(data)
        assert h1 == h2

    def test_changed_data_different_hash(self):
        data1 = {"cin": "L45201MH2003PLC142301", "name": "Test Co", "status": "Active"}
        data2 = {"cin": "L45201MH2003PLC142301", "name": "Test Co", "status": "StrikeOff"}
        assert self.indexer.compute_hash(data1) != self.indexer.compute_hash(data2)

    def test_has_changed_with_no_stored(self):
        assert self.indexer.has_changed("abc123", None) is True

    def test_has_changed_with_same_hash(self):
        assert self.indexer.has_changed("abc123", "abc123") is False

    def test_has_changed_with_different_hash(self):
        assert self.indexer.has_changed("abc123", "def456") is True
