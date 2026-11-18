"""Expose one currency conversion tool over MCP stdio."""

from datetime import date
import math

import httpx
import pycountry
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError


mcp = MCPServer("Currency Converter MCP")
RATE_URL = "https://api.frankfurter.dev/v2/rate"


@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert a finite, non-negative amount between three-letter currency codes.

    Frankfurter provides the latest available reference rate and its date.
    This rate is for reference purposes and may differ from live trading quotes.
    """
    if not math.isfinite(amount) or amount < 0:
        raise ToolError("Amount must be finite and non-negative.")

    source = from_currency.strip()
    target = to_currency.strip()
    for code in (source, target):
        if (
            not code.isascii() or len(code) != 3
            or pycountry.currencies.get(alpha_3=code.upper()) is None
        ):
            raise ToolError(f"Invalid ISO 4217 currency code: {code!r}. Use a code such as USD.")
    source, target = source.upper(), target.upper()

    if source == target:
        return (
            f"{amount} {source} = {amount} {target}\n"
            "Exchange rate: 1 (same currency)\n"
            "Exchange-rate date: N/A (no API lookup)"
        )

    try:
        response = httpx.get(f"{RATE_URL}/{source}/{target}", timeout=10.0)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise ToolError("Frankfurter timed out. Try again shortly.") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (404, 422):
            raise ToolError(f"Frankfurter has no rate for {source}/{target}.") from exc
        raise ToolError(f"Frankfurter returned HTTP {status}.") from exc
    except httpx.RequestError as exc:
        raise ToolError("Could not reach Frankfurter. Check your network connection.") from exc

    try:
        quote = response.json()
        rate = quote["rate"]
        rate_date = date.fromisoformat(quote["date"])
        if (
            quote["base"] != source or quote["quote"] != target
            or type(rate) not in (int, float)
            or not math.isfinite(rate) or rate <= 0
        ):
            raise ValueError("Unexpected currency pair or exchange rate.")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ToolError("Frankfurter returned an invalid rate response.") from exc

    converted = amount * rate
    if not math.isfinite(converted):
        raise ToolError("The converted amount is too large.")
    return (
        f"{amount} {source} = {converted:,.2f} {target}\n"
        f"Exchange rate: 1 {source} = {rate} {target}\n"
        f"Exchange-rate date: {rate_date}\n"
        "Latest available Frankfurter reference rate. Trading quotes may differ."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
