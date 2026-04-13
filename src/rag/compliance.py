"""Hedera Content Compliance checking via LLM chain.

Mirrors the rules enforced by the Hedera Content Compliance GPT:
https://chatgpt.com/g/g-685c0bffaddc8191af9d0ac7f5430b0a-hedera-content-compliance-gpt
"""

from __future__ import annotations

from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

COMPLIANCE_GPT_URL = (
    "https://chatgpt.com/g/g-685c0bffaddc8191af9d0ac7f5430b0a-hedera-content-compliance-gpt"
)

HEDERA_COMPLIANCE_RULES = """
## Hedera Content Compliance Rules

### Terminology & Branding
- The network brand name is "Hedera" (NOT "Hedera Hashgraph" — Hashgraph is the consensus algorithm, not the brand).
- The native cryptocurrency is "HBAR" (always uppercase).
- Use official service names: "Hedera Token Service (HTS)", "Hedera Consensus Service (HCS)", "Hedera Smart Contract Service", "Hedera File Service".
- Hedera uses "hashgraph consensus", NOT "blockchain". Hedera is a distributed ledger / DLT, not a blockchain. Only use "blockchain" when comparing to other networks.
- "Hedera Improvement Proposals" are "HIPs" (NOT "HEPs").
- Brand names: "HeadStarter" (not "Head Starter"), "Swirlds Labs" (not "Swirls").

### Technical Accuracy
- Hedera achieves finality in 3-5 seconds (do not claim "instant" finality).
- Hedera's consensus algorithm is aBFT (asynchronous Byzantine Fault Tolerant).
- Do not claim Hedera is "the fastest" or "the most secure" without qualification — use "one of the fastest" or cite specific benchmarks.
- Smart contracts on Hedera run on both the EVM and a native Hedera smart contract runtime.
- Do not conflate Hedera mainnet with Hedera testnet capabilities.

### Prohibited Content
- No investment advice, price predictions, or financial recommendations about HBAR.
- No unverified partnership claims — only mention partnerships confirmed by official Hedera sources.
- No FUD (Fear, Uncertainty, Doubt) or misleading negative claims about Hedera or competitors.
- No speculative roadmap claims — only reference publicly announced plans.
- No claims about Hedera's governing council membership unless verified.

### Tone & Style
- Professional, builder-focused, technically accurate.
- Factual and verifiable — every claim should be traceable to the transcript or official documentation.
- Inclusive and community-oriented language.
- Avoid hype language: "revolutionary", "game-changing", "killer app", etc.
"""


def build_compliance_check_prompt() -> PromptTemplate:
    template = f"""
You are the Hedera Content Compliance Reviewer.
Your job is to check if a blog post complies with Hedera's official content guidelines.

{HEDERA_COMPLIANCE_RULES}

Review the following blog post against ALL the rules above.

For each violation found, output a line in this exact format:
VIOLATION: [rule category] — [specific issue and how to fix it]

If the blog is fully compliant, output exactly:
COMPLIANT

Blog post to review:
{{blog}}

Source notes (for fact-checking):
{{notes}}
"""
    return PromptTemplate(
        input_variables=["blog", "notes"],
        template=template.strip(),
    )


def build_compliance_fix_prompt() -> PromptTemplate:
    template = f"""
You are a senior Hedera technical editor. Fix the draft to resolve compliance violations.
Use ONLY the notes as the source of facts. Do not invent new information.

{HEDERA_COMPLIANCE_RULES}

Compliance violations to fix:
{{violations}}

Notes (source of truth):
{{notes}}

Draft to fix:
{{draft}}

Output the corrected blog in Markdown. Preserve the existing structure and sections.
"""
    return PromptTemplate(
        input_variables=["violations", "notes", "draft"],
        template=template.strip(),
    )


def check_compliance(
    llm: ChatOpenAI,
    blog: str,
    notes: str,
) -> tuple[bool, list[str]]:
    """Check a blog post for Hedera content compliance.

    Returns:
        tuple: (is_compliant, list of violation strings)
    """
    prompt = build_compliance_check_prompt()
    chain = LLMChain(llm=llm, prompt=prompt, verbose=False)
    result = chain.predict(blog=blog, notes=notes).strip()

    if result.upper().startswith("COMPLIANT"):
        return True, []

    violations = []
    for line in result.splitlines():
        line = line.strip()
        if line.upper().startswith("VIOLATION:"):
            violations.append(line)
        elif line and not line.upper().startswith("COMPLIANT"):
            violations.append(line)

    return len(violations) == 0, violations


def fix_compliance(
    llm: ChatOpenAI,
    blog: str,
    notes: str,
    violations: list[str],
) -> str:
    """Fix compliance violations in a blog post.

    Returns:
        The corrected blog text.
    """
    prompt = build_compliance_fix_prompt()
    chain = LLMChain(llm=llm, prompt=prompt, verbose=False)
    return chain.predict(
        violations="\n".join(f"- {v}" for v in violations),
        notes=notes,
        draft=blog,
    ).strip()
