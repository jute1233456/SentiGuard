"""Smoke tests for THUCNewsLoader.

We mock `datasets.load_dataset` so the test does not hit the network.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

from hot_topic.data_source.thucnews_loader import THUCNewsLoader


class _FakeDataset:
    def __init__(self, rows):
        self._rows = rows

    def __len__(self):
        return len(self._rows)

    def shuffle(self, seed=0):
        return self  # deterministic order is fine for the smoke test

    def select(self, idxs):
        return _FakeDataset([self._rows[i] for i in idxs])

    def __iter__(self):
        return iter(self._rows)


def test_iter_docs_basic():
    fake_rows = [
        {"title": "标题1", "content": "内容1", "label": "体育"},
        {"title": "标题2", "content": "内容2", "label": "财经"},
        {"title": "标题3", "content": "",      "label": "社会"},  # falls back to title
    ]
    # `datasets` is imported inside iter_docs(); inject a stub module so the
    # import succeeds and load_dataset returns our fake rows.
    fake_mod = types.ModuleType("datasets")
    fake_mod.load_dataset = lambda *a, **kw: _FakeDataset(fake_rows)
    with patch.dict(sys.modules, {"datasets": fake_mod}):
        loader = THUCNewsLoader(hf_repo="dummy", split="train")
        df = loader.to_dataframe(sample_size=3)

    assert len(df) == 3
    assert df.iloc[0]["title"] == "标题1"
    assert df.iloc[0]["content"] == "内容1"
    assert df.iloc[2]["content"] == "标题3"  # fallback
    assert (df["source"] == "thucnews").all()
    assert (df["lang"] == "zh").all()
    assert df.iloc[0]["category"] == "体育"
    assert df.iloc[0]["doc_id"].startswith("thucnews-")
