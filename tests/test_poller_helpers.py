import pytest
import poller
from urllib.parse import unquote


def test_parse_stockcell_standard_codes():
    assert poller.parse_stockcell("10123") == "Left A/23"
    assert poller.parse_stockcell("20312") == "Right C/12"


def test_parse_stockcell_invalid_and_empty():
    assert poller.parse_stockcell("") == ""
    assert poller.parse_stockcell("abc") == "abc"
    assert poller.parse_stockcell("123") == "123"


def test_parse_stockcell_non_numeric_row():
    assert poller.parse_stockcell("1A012") == "1A012"


def test_safe_url_redacts_sensitive_params():
    url = poller._safe_url("http://example.com/api?f=login&tkn=secret&api_key=mykey&normal=1")
    decoded = unquote(url)
    assert "[REDACTED]" in decoded
    assert "normal=1" in decoded
    assert "tkn=secret" not in decoded
    assert "api_key=mykey" not in decoded


def test_safe_url_returns_url_on_error(monkeypatch):
    monkeypatch.setattr(poller, "urlparse", lambda u: (_ for _ in ()).throw(ValueError("bad")))
    assert poller._safe_url("http://example.com") == "[URL no disponible]"
