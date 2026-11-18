"""Test conversion and error handling without contacting Frankfurter."""

from unittest.mock import Mock

import httpx
from mcp.server.mcpserver.exceptions import ToolError
import pytest

from server import convert_currency


@pytest.fixture(autouse=True)
def mock_get(monkeypatch):
    get = Mock(side_effect=AssertionError("Unexpected HTTP request"))
    monkeypatch.setattr(httpx, "get", get)
    return get


@pytest.mark.parametrize(
    ("source", "target", "base", "quote", "rate", "expected"),
    [
        ("USD", "EUR", "USD", "EUR", 0.912345, "91.23"),
        ("EUR", "GBP", "EUR", "GBP", 0.85678, "85.68"),
        (" usd ", " eur ", "USD", "EUR", 0.91, "91.00"),
        ("USD", "EUR", "USD", "EUR", 0.000123456, "0.01"),
    ],
)
def test_conversion(mock_get, source, target, base, quote, rate, expected):
    url = f"https://api.frankfurter.dev/v2/rate/{base}/{quote}"
    mock_get.side_effect = None
    mock_get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", url),
        json={"base": base, "quote": quote, "rate": rate, "date": "2026-01-15"},
    )

    result = convert_currency(100.0, source, target)

    mock_get.assert_called_once_with(url, timeout=10.0)
    assert f"100.0 {base} = {expected} {quote}" in result
    assert f"1 {base} = {rate} {quote}" in result
    assert "Exchange-rate date: 2026-01-15" in result
    assert "reference rate" in result


def test_same_currency(mock_get):
    result = convert_currency(12.345, " usd ", "USD")
    assert "12.345 USD = 12.345 USD" in result
    assert "Exchange rate: 1" in result
    assert "Exchange-rate date: N/A" in result
    mock_get.assert_not_called()


@pytest.mark.parametrize("amount", [-1, float("inf"), float("-inf"), float("nan")])
def test_invalid_amount(mock_get, amount):
    with pytest.raises(ToolError, match="finite and non-negative"):
        convert_currency(amount, "USD", "EUR")
    mock_get.assert_not_called()


@pytest.mark.parametrize(("source", "target"), [("US", "EUR"), ("USD", "../"), ("ZZZ", "ZZZ")])
def test_invalid_currency(mock_get, source, target):
    with pytest.raises(ToolError, match="Invalid ISO 4217 currency code"):
        convert_currency(100, source, target)
    mock_get.assert_not_called()


@pytest.mark.parametrize(
    ("status", "message"),
    [(404, "no rate for USD/XXX"), (422, "no rate for USD/XXX"), (503, "HTTP 503")],
)
def test_api_failure(mock_get, status, message):
    mock_get.side_effect = None
    mock_get.return_value = httpx.Response(
        status, request=httpx.Request("GET", "https://api.frankfurter.dev/v2/rate/USD/XXX")
    )
    with pytest.raises(ToolError, match=message):
        convert_currency(100, "USD", "XXX")


@pytest.mark.parametrize(
    ("error", "message"),
    [(httpx.ReadTimeout("timeout"), "timed out"), (httpx.ConnectError("offline"), "Could not reach")],
)
def test_network_failure(mock_get, error, message):
    mock_get.side_effect = error
    with pytest.raises(ToolError, match=message):
        convert_currency(100, "USD", "EUR")


def test_invalid_api_response(mock_get):
    mock_get.side_effect = None
    mock_get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "https://api.frankfurter.dev/v2/rate/USD/EUR"),
        json={"base": "USD", "quote": "EUR", "rate": 0, "date": "2026-01-15"},
    )
    with pytest.raises(ToolError, match="invalid rate response"):
        convert_currency(100, "USD", "EUR")
