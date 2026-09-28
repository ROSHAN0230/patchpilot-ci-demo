"""
Tavily-Powered Upstream Migration Evidence Retrieval Engine.
Assembles authoritative EvidencePacks tagged to specific FailureClusters and UpgradeSpecs.
"""

import time
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Optional
from patchpilot.types import (
    DependencyDelta,
    FailureRecord,
    UpgradeSpec,
    FailureCluster,
    EvidenceItem,
    EvidencePack,
)
from patchpilot.contracts import EvidenceEngine


class TavilyEvidenceEngine(EvidenceEngine):
    """Retrieves and structures authoritative migration documentation using Tavily Search API."""

    AUTHORITATIVE_DOMAINS = {
        "pydantic": ["docs.pydantic.dev", "pydantic.dev"],
        "sqlalchemy": ["docs.sqlalchemy.org", "sqlalchemy.org"],
        "fastapi": ["fastapi.tiangolo.com"],
    }

    def __init__(self, api_key: str):
        self.api_key = api_key.strip()

    def assemble_evidence_pack(
        self,
        spec: UpgradeSpec,
        clusters: List[FailureCluster],
    ) -> EvidencePack:
        """
        Gathers authoritative evidence per migration cluster and builds a structured EvidencePack.
        """
        pack = EvidencePack(spec=spec)
        if not self.api_key:
            pack.status = "TAVILY_UNAVAILABLE"
            pack.error_message = "No Tavily API key provided"
            return pack

        from tavily import TavilyClient
        try:
            client = TavilyClient(api_key=self.api_key)
        except Exception as e:
            pack.status = "TAVILY_UNAVAILABLE"
            pack.error_message = f"Failed to initialize Tavily client: {str(e)}"
            return pack

        domains = self.AUTHORITATIVE_DOMAINS.get(spec.package_name.lower(), [])
        item_counter = 1
        any_success = False
        had_error = False

        for cluster in clusters:
            pack.cluster_evidence_map[cluster.cluster_id] = []
            # Tailor search query to the cluster's specific category and symbols
            cat_query = cluster.failure_category.replace("_", " ")
            sym_query = " ".join(cluster.symbols[:2])
            query = f"{spec.package_name} {spec.new_version} migration guide {cat_query} {sym_query}".strip()

            try:
                search_kwargs = {
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 2,
                }
                if domains:
                    search_kwargs["include_domains"] = domains

                res = client.search(**search_kwargs)
                results = res.get("results", [])

                for r in results:
                    url = r.get("url", "")
                    title = r.get("title", f"{spec.package_name} Migration Documentation")
                    content = r.get("content", "")

                    authority = "official_docs"
                    if "migration" in url.lower() or "migrate" in url.lower():
                        authority = "migration_guide"
                    elif "changelog" in url.lower() or "release" in url.lower():
                        authority = "changelog"

                    evidence_id = f"ev_{spec.package_name.lower()}_{item_counter}"
                    item_counter += 1

                    item = EvidenceItem(
                        evidence_id=evidence_id,
                        cluster_id=cluster.cluster_id,
                        query=query,
                        url=url,
                        title=title,
                        retrieved_timestamp=datetime.now(timezone.utc).isoformat(),
                        relevant_content=content,
                        source_authority=authority,
                    )
                    pack.items.append(item)
                    pack.cluster_evidence_map[cluster.cluster_id].append(item)
                    cluster.evidence_references.append(evidence_id)
                    any_success = True

            except Exception as e:
                # FAIL CLOSED: Do NOT fabricate official documentation on failure
                had_error = True
                pack.error_message = f"Tavily search failed: {str(e)}"

        if pack.items:
            pack.status = "TAVILY_RETRIEVED"
        elif had_error:
            pack.status = "TAVILY_UNAVAILABLE"
        else:
            pack.status = "TAVILY_EMPTY"

        return pack

    def search_migration_docs(
        self, delta: DependencyDelta, failures: List[FailureRecord]
    ) -> Tuple[str, List[Dict[str, str]]]:
        """Backwards-compatible interface for simple text context + citations."""
        if not self.api_key:
            return "", []

        categories = list({f.category for f in failures})
        cat_str = " ".join(categories[:2]).replace("_", " ")
        symbols = list({f.symbol for f in failures if f.symbol})
        sym_str = " ".join(symbols[:2])

        query = f"{delta.package_name} V2 migration guide {cat_str} {sym_str}".strip()

        from tavily import TavilyClient
        try:
            client = TavilyClient(api_key=self.api_key)
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
        except Exception:
            return "", []
