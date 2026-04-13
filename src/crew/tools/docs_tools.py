"""Tool for querying the Hedera official documentation FAISS index."""

from crewai.tools import tool


@tool("Query Hedera Documentation")
def query_hedera_docs(query: str) -> str:
    """Search the official Hedera documentation (docs.hedera.com, hedera.com/blog,
    hedera.com/learning) for information relevant to the given query.
    Returns matching documentation excerpts.

    Args:
        query: The search query to find relevant Hedera documentation.
    """
    from rag.hedera_docs import get_relevant_context

    context, num_chunks, errors = get_relevant_context(query, k=5)
    if not context:
        error_msg = "; ".join(errors) if errors else "No relevant documentation found."
        return f"No results: {error_msg}"
    return context
