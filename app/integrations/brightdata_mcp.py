import os, asyncio
from contextlib import asynccontextmanager

# Official MCP Python SDK
from mcp import Client

def _endpoint() -> str:
    return os.getenv("BRIGHTDATA_MCP_URL") or f"https://mcp.brightdata.com/mcp?token={os.getenv('BRIGHTDATA_MCP_TOKEN','')}"

@asynccontextmanager
async def _client():
    url = _endpoint()
    if not url:
        raise RuntimeError("Bright Data MCP token/URL not set")
    c = await Client.connect_sse(url)
    try:
        yield c
    finally:
        await c.close()

async def mcp_vendor_enrich(query: str) -> dict:
    """Search the web and return a tiny enrichment dict (website, snippet)."""
    async with _client() as c:
        tools = await c.list_tools()
        names = [t.name for t in tools]
        # Prefer a search tool
        search = next((n for n in names if "search" in n.lower()), None)
        if not search:
            return {"_mcp_tools": names}

        res = await c.call_tool(search, {"query": query, "limit": 3})
        items = res.data if hasattr(res, "data") else res
        if not items:
            return {"_mcp": "no_results"}

        first = items[0]
        url = (first.get("url") or first.get("link") or first.get("pageUrl") or "")
        title = first.get("title") or first.get("headline")
        # Try to open the page if there’s a browser/open tool
        opener = next((n for n in names if "open" in n.lower() or "browser" in n.lower()), None)
        snippet = None
        if opener and url:
            try:
                page = await c.call_tool(opener, {"url": url})
                snippet = (page.get("text") or page.get("content") or "")[:500]
            except Exception:
                pass
        return {"website": url, "title": title, "snippet": snippet}
