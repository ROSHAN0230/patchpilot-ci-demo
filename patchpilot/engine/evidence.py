"""
Tavily-Powered Upstream Migration Evidence Retrieval Engine.
"""

import time
from typing import List, Tuple, Dict
from patchpilot.types import DependencyDelta, FailureRecord, UpstreamCitation
from patchpilot.contracts import EvidenceEngine


class TavilyEvidenceEngine(EvidenceEngine):
    """Retrieves authoritative migration documentation using Tavily Search API."""

    def __init__(self, api_key: str):
        self.api_key = api_key.strip()

    def search_migration_docs(
        self, delta: DependencyDelta, failures: List[FailureRecord]
    ) -> Tuple[str, List[Dict[str, str]]]:
        if not self.api_key:
            return "No Tavily API key provided. Relying on baseline knowledge.", []

        # Formulate query based on failure categories
        categories = list({f.category for f in failures})
        cat_str = " ".join(categories[:2]).replace("_", " ")
        symbols = list({f.symbol for f in failures if f.symbol})
        sym_str = " ".join(symbols[:2])

        query = f"{delta.package_name} V2 migration guide {cat_str} {sym_str}".strip()

        from tavily import TavilyClient

        client = TavilyClient(api_key=self.api_key)
        try:
            res = client.search(query=query, search_depth="basic", max_results=2)
            results = res.get("results", [])

            snippets = []
            citations = []
            for r in results:
                title = r.get("title", "Migration Doc")
                url = r.get("url", "")
                content = r.get("content", "")
                snippets.append(f"Source [{title}] ({url}):\n{content}")
                citations.append({"title": title, "url": url, "snippet": content[:300]})

            combined_docs = "\n\n".join(snippets)
            return combined_docs, citations
        except Exception as e:
            return f"Evidence retrieval notice: {str(e)}", []
