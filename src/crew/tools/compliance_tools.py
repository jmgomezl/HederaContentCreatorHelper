"""Tool for retrieving Hedera content compliance rules."""

from crewai.tools import tool


@tool("Get Hedera Compliance Rules")
def get_compliance_rules() -> str:
    """Retrieve the official Hedera content compliance rules covering
    terminology, branding, technical accuracy, prohibited content, and tone.
    Use these rules to validate blog content before publishing.
    """
    from rag.compliance import HEDERA_COMPLIANCE_RULES

    return HEDERA_COMPLIANCE_RULES
