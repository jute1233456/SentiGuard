"""Smoke tests for GDELTClient (mocked HTTP, no network required)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from hot_topic.data_source.gdelt_client import GDELTClient, _parse_seendate


def test_parse_seendate_valid():
    assert _parse_seendate("20260616T120000Z").startswith("2026-06-16T12:00:00")


def test_parse_seendate_invalid():
    assert _parse_seendate("garbage") == "garbage"
    assert _parse_seendate("") == ""


def _mock_response(payload: dict, content_type: str = "application/json"):
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"content-type": content_type}
    resp.text = json.dumps(payload)
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def test_fetch_articles_parses_payload():
    payload = {
        "articles": [
            {
                "url": "https://example.com/a",
                "title": "测试新闻一",
                "seendate": "20260616T120000Z",
                "sourcecountry": "China",
                "language": "Chinese",
            },
            {
                "url": "https://example.com/b",
                "title": "测试新闻二",
                "seendate": "20260616T130000Z",
                "sourcecountry": "China",
                "language": "Chinese",
            },
        ]
    }
    client = GDELTClient()
    with patch.object(client.session, "get", return_value=_mock_response(payload)):
        df = client.to_dataframe(timespan="1h", max_records=10)
    assert len(df) == 2
    assert df.iloc[0]["title"] == "测试新闻一"
    assert df.iloc[0]["source"] == "gdelt"
    assert df.iloc[0]["lang"] == "ch"  # "Chinese"[:2].lower()
    assert df.iloc[0]["publish_time"].startswith("2026-06-16T12:00:00")


def test_non_json_response_raises():
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"content-type": "text/html"}
    resp.text = "<html>oops</html>"
    resp.raise_for_status = MagicMock()
    client = GDELTClient(retry_attempts=1, retry_backoff=0)
    with patch.object(client.session, "get", return_value=resp):
        try:
            client.fetch_articles(timespan="1h")
        except RuntimeError as e:
            assert "GDELT" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_empty_articles():
    client = GDELTClient()
    with patch.object(client.session, "get", return_value=_mock_response({"articles": []})):
        df = client.to_dataframe(timespan="1h")
    assert df.empty
    # schema columns still present
    from hot_topic.config import DOC_COLUMNS
    assert list(df.columns) == DOC_COLUMNS
