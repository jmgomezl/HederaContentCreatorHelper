"""Fetch and index official Hedera documentation for RAG enrichment."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

HEDERA_SOURCES = {
    "docs": [
        "https://docs.hedera.com/hedera",
        "https://docs.hedera.com/hedera/sdks",
        "https://docs.hedera.com/hedera/core-concepts",
        "https://docs.hedera.com/hedera/networks",
        "https://docs.hedera.com/hedera/sdks/consensus",
        "https://docs.hedera.com/hedera/sdks/tokens",
        "https://docs.hedera.com/hedera/sdks/smart-contracts",
        "https://docs.hedera.com/hedera/sdks/file-service",
        "https://docs.hedera.com/hedera/open-source-solutions",
    ],
    "blog": [
        "https://hedera.com/blog",
    ],
    "learning": [
        "https://hedera.com/learning",
        "https://hedera.com/learning/hedera-hashgraph",
        "https://hedera.com/learning/smart-contracts",
        "https://hedera.com/learning/tokens",
        "https://hedera.com/learning/consensus",
    ],
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}
REQUEST_TIMEOUT = 15


@dataclass
class DocsCache:
    """In-memory cache for the FAISS retriever so it's built once per session."""
    retriever: object | None = None
    doc_count: int = 0
    errors: list[str] = field(default_factory=list)


_cache = DocsCache()


def _scrape_page(url: str) -> str:
    """Scrape text content from a single URL."""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove scripts, styles, nav, footer
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # Try main content areas first
    content = None
    for selector in ["main", "article", "[role='main']", ".content", ".markdown-body"]:
        content = soup.select_one(selector)
        if content:
            break

    text = (content or soup.body or soup).get_text(separator="\n", strip=True)
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    if len(text) < 50:
        return ""

    return f"Source: {url}\n\n{text[:8000]}"


def _discover_links(base_url: str, soup: BeautifulSoup, max_links: int = 15) -> list[str]:
    """Extract internal links from a page to crawl deeper."""
    links = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith("/"):
            href = base_url.rstrip("/") + href
        if base_url in href and href not in links and "#" not in href:
            links.add(href)
        if len(links) >= max_links:
            break
    return list(links)


def fetch_hedera_docs(
    sources: dict[str, list[str]] | None = None,
) -> tuple[list[str], list[str]]:
    """Scrape Hedera official documentation pages.

    Returns:
        tuple: (list of document texts, list of error messages)
    """
    sources = sources or HEDERA_SOURCES
    documents: list[str] = []
    errors: list[str] = []

    all_urls: list[str] = []
    for category_urls in sources.values():
        all_urls.extend(category_urls)

    for url in all_urls:
        text = _scrape_page(url)
        if text:
            documents.append(text)
        else:
            errors.append(f"No content from {url}")

    # For blog and learning pages, try to discover and scrape linked articles
    for category in ["blog", "learning"]:
        for base_url in sources.get(category, []):
            try:
                resp = requests.get(base_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
                soup = BeautifulSoup(resp.text, "html.parser")
                child_links = _discover_links(base_url, soup, max_links=10)
                for link in child_links:
                    if link not in all_urls:
                        text = _scrape_page(link)
                        if text:
                            documents.append(text)
            except Exception as exc:
                errors.append(f"Error discovering links from {base_url}: {exc}")

    return documents, errors


def build_docs_retriever(
    documents: list[str],
    chunk_size: int = 1500,
    chunk_overlap: int = 200,
    k: int = 5,
) -> object:
    """Build a FAISS retriever from document texts."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = []
    for doc in documents:
        chunks.extend(splitter.split_text(doc))

    if not chunks:
        raise ValueError("No document chunks to index.")

    embeddings = OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-small")
    vector_store = FAISS.from_texts(chunks, embeddings)
    return vector_store.as_retriever(search_kwargs={"k": k})


def get_relevant_context(
    query: str,
    k: int = 5,
    force_refresh: bool = False,
) -> tuple[str, int, list[str]]:
    """Retrieve relevant Hedera documentation context for a query.

    Uses a cached FAISS index (built once per session).

    Returns:
        tuple: (context_text, num_chunks_retrieved, errors)
    """
    global _cache

    if _cache.retriever is None or force_refresh:
        documents, errors = fetch_hedera_docs()
        _cache.errors = errors
        if not documents:
            return "", 0, errors + ["No Hedera documentation could be fetched."]
        try:
            _cache.retriever = build_docs_retriever(documents, k=k)
            _cache.doc_count = len(documents)
        except Exception as exc:
            return "", 0, [f"Failed to build docs index: {exc}"]

    try:
        results = _cache.retriever.get_relevant_documents(query)
    except Exception as exc:
        return "", 0, [f"Retrieval error: {exc}"]

    if not results:
        return "", 0, []

    context_parts = []
    for i, doc in enumerate(results, 1):
        context_parts.append(f"[Doc {i}] {doc.page_content}")

    context = "\n\n".join(context_parts)
    return context, len(results), _cache.errors


def reset_cache() -> None:
    """Clear the cached FAISS index (e.g., to force a refresh)."""
    global _cache
    _cache = DocsCache()
