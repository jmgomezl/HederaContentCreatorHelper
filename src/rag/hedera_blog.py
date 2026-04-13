"""Utilities for generating Medium-ready Hedera technical blogs from YouTube livestreams."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import parse_qs, urlparse

from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import ChatOpenAI
from youtube_transcript_api import YouTubeTranscriptApi


VIDEO_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{11}$")
TIMESTAMP_PATTERN = re.compile(r"\[(?:t=\d+(?:\.\d+)?)\]|\(t=\d+(?:\.\d+)?\)")
TIMESTAMP_VALUE_PATTERN = re.compile(r"\[t=(\d+(?:\.\d+)?)\]|\(t=(\d+(?:\.\d+)?)\)")
PROPER_TOKEN_PATTERN = re.compile(
    r"\b(?:[A-Z][a-z][a-z]+|[A-Z]{2,}|[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*)\b"
)

STOPWORDS = {
    "A",
    "An",
    "And",
    "As",
    "At",
    "Be",
    "But",
    "By",
    "For",
    "From",
    "He",
    "Her",
    "His",
    "I",
    "In",
    "Is",
    "It",
    "Its",
    "Key",
    "No",
    "Not",
    "Of",
    "On",
    "Or",
    "Our",
    "Resources",
    "She",
    "So",
    "That",
    "The",
    "Their",
    "These",
    "They",
    "This",
    "Those",
    "TL",
    "DR",
    "To",
    "We",
    "With",
    "You",
    "Your",
}

HEADING_RULES = [
    ("Builder ecosystem & product stack", ["cabula", "headstarter", "builder labs", "wallet", "marketplace", "sdk", "nft toolkit"]),
    ("Platform readiness & native services", ["native services", "token service", "consensus service", "evm", "equivalence", "scalable", "tps", "protocol", "mirror nodes", "hashgraph"]),
    ("Compliance, regulation & business", ["regulation", "compliance", "legal", "institutional", "business", "go-to-market", "monetize", "rwa", "tokenization"]),
    ("UX, onboarding & agentic commerce", ["ux", "custody", "wallet", "gmail", "sponsored fees", "agentic", "onboarding", "fees"]),
    ("Developer onboarding & community", ["playground", "documentation", "discord", "hackathon", "dev day", "hederacon", "sdk", "examples"]),
]


@dataclass(frozen=True)
class BlogConfig:
    model_name: str = "gpt-5-mini"
    temperature: float = 1.0
    notes_chunk_size: int = 4000
    notes_chunk_overlap: int = 200
    max_chunks: int = 12
    max_iterations: int = 2
    min_sections: int = 3
    max_sections: int = 5


def extract_video_id(url: str) -> str | None:
    """Extract a YouTube video ID from common URL formats or accept a raw ID."""
    if not url:
        return None

    candidate = url.strip()
    if VIDEO_ID_PATTERN.match(candidate):
        return candidate

    try:
        parsed = urlparse(candidate)
    except Exception:
        return None

    hostname = (parsed.hostname or "").lower()
    path = parsed.path or ""

    if "youtu.be" in hostname:
        vid = path.lstrip("/").split("/")[0]
        return vid if VIDEO_ID_PATTERN.match(vid) else None

    if "youtube.com" in hostname:
        if path == "/watch":
            query = parse_qs(parsed.query)
            vid = query.get("v", [None])[0]
            return vid if vid and VIDEO_ID_PATTERN.match(vid) else None

        for prefix in ("/live/", "/embed/", "/shorts/"):
            if path.startswith(prefix):
                vid = path[len(prefix):].split("/")[0]
                return vid if VIDEO_ID_PATTERN.match(vid) else None

    return None


def fetch_transcript(video_id: str) -> tuple[list[dict] | None, str | None]:
    """Fetch the English transcript for the given video ID."""
    transcript_list = None
    list_error: Exception | None = None

    for target in (YouTubeTranscriptApi, YouTubeTranscriptApi()):
        for method_name in ("list_transcripts", "list"):
            if not hasattr(target, method_name):
                continue
            try:
                transcript_list = getattr(target, method_name)(video_id)
                break
            except Exception as exc:  # noqa: BLE001
                list_error = exc
        if transcript_list is not None:
            break

    if transcript_list is not None:
        if hasattr(transcript_list, "find_manually_created_transcript"):
            transcript = None
            try:
                transcript = transcript_list.find_manually_created_transcript(["en"])
            except Exception:
                try:
                    transcript = transcript_list.find_generated_transcript(["en"])
                except Exception:
                    try:
                        transcript = transcript_list.find_transcript(["en"])
                    except Exception:
                        transcript = None
            if transcript is None:
                return None, "No English transcript is available for this video."
            try:
                return transcript.fetch(), None
            except Exception as exc:  # noqa: BLE001
                return None, f"Unable to fetch the transcript: {exc}"

        # Fallback: iterate transcript objects like the older API.
        selected = None
        try:
            for t in transcript_list:
                language_code = getattr(t, "language_code", None)
                is_generated = getattr(t, "is_generated", None)
                if language_code != "en":
                    continue
                if selected is None or not is_generated:
                    selected = t
                    if not is_generated:
                        break
        except Exception:
            selected = None

        if selected is None:
            return None, "No English transcript is available for this video."
        try:
            return selected.fetch(), None
        except Exception as exc:  # noqa: BLE001
            return None, f"Unable to fetch the transcript: {exc}"

    # Final fallback: direct get_transcript if available.
    last_error: Exception | None = None
    for target in (YouTubeTranscriptApi, YouTubeTranscriptApi()):
        if hasattr(target, "get_transcript"):
            try:
                return target.get_transcript(video_id, languages=["en"]), None
            except Exception as exc:  # noqa: BLE001
                last_error = exc

    if last_error:
        return None, f"Unable to fetch the transcript: {last_error}"
    if list_error:
        return None, f"Unable to access transcripts for this video: {list_error}"
    return None, "Unable to access transcripts (youtube-transcript-api is likely outdated)."


def format_transcript(entries: Iterable[dict], include_timestamps: bool = False) -> str:
    """Convert transcript entries into a clean, single text block."""
    lines: list[str] = []
    for entry in entries:
        text = entry.get("text") if isinstance(entry, dict) else getattr(entry, "text", None)
        start = entry.get("start") if isinstance(entry, dict) else getattr(entry, "start", None)
        if not text:
            continue
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned or cleaned.lower() in {"[music]", "[applause]"}:
            continue
        if include_timestamps and start is not None:
            lines.append(f"{cleaned} (t={start:.2f})")
        else:
            lines.append(cleaned)
    return "\n".join(lines)


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split text into overlapping chunks for summarization."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.split_text(text)


def build_notes_prompt(strict_mode: bool = False) -> PromptTemplate:
    template = """
You are a technical note-taker specializing in Hedera and web3.
Extract only concrete technical details from the transcript chunk.
- Focus on product names, APIs, architecture decisions, protocols, tooling, demos, metrics, and explicit timelines.
- Keep it factual and concise.
- If nothing technical is present, respond with "No technical details found in this chunk."

Transcript chunk:
{chunk}
"""
    if strict_mode:
        template = """
You are a technical note-taker specializing in Hedera and web3.
Extract only concrete technical details from the transcript chunk.
- Every bullet must include a timestamp in the form [t=123.45] copied from the transcript line.
- Use only facts explicitly stated in the chunk.
- Keep it factual and concise.
- If nothing technical is present, respond with "No technical details found in this chunk."

Transcript chunk (timestamps are shown as "(t=...)"):
{chunk}
"""
    return PromptTemplate(input_variables=["chunk"], template=template.strip())


def build_blog_prompt(strict_mode: bool = False) -> PromptTemplate:
    template = """
You are a senior technical writer who publishes on Medium's top blockchain publications.
Write a compelling, publish-ready technical blog post based ONLY on the notes below.

Audience: {audience}
Length: {length}
Focus areas (if any): {focus}

STRUCTURE (follow this precisely):
1. H1 TITLE: Specific, compelling, and searchable. Not generic. Include the actual technology or feature name.
2. ITALIC SUBTITLE: One sentence that hooks the reader — state the problem this solves or why they should care.
3. INTRODUCTION (2-3 paragraphs): Set the context. Why does this topic matter NOW? What problem does it solve for builders? Draw the reader in with a concrete scenario or pain point.
4. TL;DR: 4-5 crisp bullets that summarize the key takeaways. Each bullet should be a complete, useful insight — not a vague pointer.
5. BODY SECTIONS (3-5 H2 sections):
   - Each H2 title must be specific and descriptive (e.g., "How the Forking Library Simulates Mainnet State" NOT "Technical Details").
   - Each section: 2-4 substantive paragraphs with concrete details, not just surface-level summaries.
   - Include specific technical details: API names, function signatures, configuration steps, architecture decisions.
   - Use bullet lists for steps, comparisons, or feature lists.
   - Include code snippets ONLY if explicitly present in the notes.
   - Use transitions between sections so the article flows as a narrative, not a list of facts.
6. KEY TAKEAWAYS: 3-5 actionable bullets. Each should tell the reader what to DO, not just what exists.
7. CLOSING PARAGRAPH: End with a clear call-to-action — where to start, what to build, or where to learn more.
8. RESOURCES: List reference links verbatim if provided.

WRITING QUALITY:
- Write like a human expert, not an AI. Vary sentence length. Use active voice.
- Be specific: "The forking library intercepts JSON-RPC calls and routes them to a mainnet mirror node" is better than "The library provides powerful testing capabilities."
- No filler phrases: "It is worth noting that", "In conclusion", "As we can see", "This is a powerful feature" — cut all of these.
- No hype: "revolutionary", "game-changing", "cutting-edge" — replace with concrete descriptions of what the thing actually does.
- Every paragraph must add NEW information. If a paragraph could be deleted without losing anything, delete it.
- Do not invent facts, metrics, links, or features that are not in the notes.
"""
    if strict_mode:
        template += """
- Strict mode: Every sentence must include at least one timestamp citation in the form [t=123.45] that appears in the notes.
- Remove any sentence that cannot be tied to a timestamped note.
- Length multiplier: {length_multiplier} (if >1, add more timestamped details without repeating).

Verbosity: {verbosity}

Reference links:
{reference_links}

Notes:
{notes}
"""
    else:
        template += """

Length multiplier: {length_multiplier} (if >1, add more detail without repeating).

Verbosity: {verbosity}

Reference links:
{reference_links}

Notes:
{notes}
"""
    return PromptTemplate(
        input_variables=[
            "audience",
            "length",
            "focus",
            "reference_links",
            "notes",
            "verbosity",
            "length_multiplier",
        ],
        template=template.strip(),
    )


def build_review_prompt(strict_mode: bool = False) -> PromptTemplate:
    template = """
You are a meticulous technical editor and fact-checker.
Review the draft blog against the notes. The notes are the ONLY allowed source of facts.

Strict mode:
- Every sentence must include at least one timestamp citation in the form [t=123.45] that appears in the notes.
- Flag any sentence or bullet without a timestamp or with timestamps not present in the notes.

Output format:
1) Verdict: APPROVE or REVISE
2) Risks: bullet list of any claims not supported by the notes (or say "None")
3) Rewrite instructions: bullet list of concrete fixes to make it accurate, readable, and friendly

Notes:
{notes}

Draft:
{draft}
"""
    if not strict_mode:
        template = template.replace(
            "\nStrict mode:\n- Every sentence must include at least one timestamp citation in the form [t=123.45] that appears in the notes.\n- Flag any sentence or bullet without a timestamp or with timestamps not present in the notes.\n",
            "",
        )
    return PromptTemplate(input_variables=["notes", "draft"], template=template.strip())


def build_publisher_prompt(strict_mode: bool = False) -> PromptTemplate:
    template = """
You are the editor-in-chief of a top blockchain publication on Medium.
Take the draft and review feedback, and produce the FINAL publish-ready blog post.

Your job is to make this article something a developer would actually bookmark and share.

Rules:
- Use ONLY facts present in the notes. Remove or rewrite anything flagged in the review.
- Output Markdown.
- The article must have: H1 title, italic subtitle hook, introduction (2-3 paragraphs), TL;DR (4-5 bullets), 3-5 substantive H2 body sections, Key takeaways (actionable bullets), closing CTA, and Resources if links provided.
- Each body section must have 2-4 paragraphs with concrete technical details — not surface summaries.
- H2 titles must be specific (e.g., "Intercepting JSON-RPC Calls with the Forking Library" NOT "How It Works").
- Write like a human expert: vary sentence length, use active voice, be specific.
- Cut ALL filler: "It is worth noting", "In conclusion", "As we can see", "This is powerful". Every sentence must earn its place.
- No hype words: "revolutionary", "game-changing", "cutting-edge". Describe what the thing does instead.
- Include code snippets ONLY if explicitly present in the notes.
- Do not invent facts, metrics, links, or features that are not in the notes.
"""
    if strict_mode:
        template += """
- Strict mode: Every sentence must include at least one timestamp citation in the form [t=123.45] that appears in the notes.
- Remove any sentence that cannot be tied to a timestamped note.
- Verbosity guidance: 
  - Concise: keep it tight, only the essentials.
  - Standard: balanced detail and readability.
  - Detailed: include as many timestamped technical details as possible without repeating.
- Length multiplier: {length_multiplier} (if >1, add more timestamped detail without repeating).

Audience: {audience}
Length: {length}
Focus areas (if any): {focus}
Verbosity: {verbosity}
Length multiplier: {length_multiplier}

Reference links:
{reference_links}

Notes:
{notes}

Review feedback:
{review}
"""
    else:
        template += """

Audience: {audience}
Length: {length}
Focus areas (if any): {focus}
Verbosity: {verbosity}
Length multiplier: {length_multiplier}

Reference links:
{reference_links}

Notes:
{notes}

Review feedback:
{review}
"""
    return PromptTemplate(
        input_variables=[
            "audience",
            "length",
            "focus",
            "reference_links",
            "notes",
            "review",
            "verbosity",
            "length_multiplier",
        ],
        template=template.strip(),
    )


def build_title_prompt() -> PromptTemplate:
    template = """
You are an editor crafting publication titles for a technical Medium blog.
Generate {count} concise, compelling title options based ONLY on the blog text.
Do not add new facts or names that do not appear in the blog.

Blog:
{blog}
"""
    return PromptTemplate(input_variables=["blog", "count"], template=template.strip())


def build_refine_prompt(strict_mode: bool = False) -> PromptTemplate:
    template = """
You are a senior technical editor at a top blockchain publication. Fix the draft to address the issues list.
Use ONLY the notes as source of facts.

Required structure:
- H1 title (specific, not generic).
- Italic subtitle hook.
- Introduction (2-3 paragraphs setting context).
- TL;DR with 4-5 actionable bullets.
- {min_sections}-{max_sections} H2 body sections with unique, descriptive titles.
- Each body section: 2-4 substantive paragraphs with concrete technical details.
- Key takeaways (actionable bullets).
- Closing paragraph with clear CTA.
- Resources section ONLY if reference links are provided.

Rules:
- Do not invent facts, metrics, links, or features not in the notes.
- Include code snippets ONLY if explicitly present in the notes.
- H2 titles must be specific: "How the Forking Library Intercepts RPC Calls" NOT "Technical Details".
- Cut ALL filler: "It is worth noting", "In conclusion", "As we can see". Every sentence must add information.
- No hype: "revolutionary", "game-changing". Describe what things do instead.
- Write like a human expert: vary sentence length, active voice, be specific.
- Keep sentences scannable (aim for ~20-28 words max).
"""
    if strict_mode:
        template += """
- Strict mode: Every sentence must include at least one timestamp citation in the form [t=123.45] that appears in the notes.
- Remove any sentence that cannot be tied to a timestamped note.
"""
    template += """
Audience: {audience}
Length: {length}
Focus areas (if any): {focus}
Verbosity: {verbosity}
Length multiplier: {length_multiplier}

Reference links:
{reference_links}

Issues to fix:
{issues}

Notes:
{notes}

Draft:
{draft}
"""
    return PromptTemplate(
        input_variables=[
            "audience",
            "length",
            "focus",
            "verbosity",
            "length_multiplier",
            "reference_links",
            "issues",
            "notes",
            "draft",
            "min_sections",
            "max_sections",
        ],
        template=template.strip(),
    )


def build_linguistic_prompt(strict_mode: bool = False) -> PromptTemplate:
    template = """
You are a professional editor polishing a technical blog for Medium publication.
Your goal: make this read like it was written by an experienced developer, not generated by AI.

Rules:
- Keep the existing structure, section order, and all facts intact.
- Keep TL;DR bullets (do not add or remove bullets).
- Do not invent any facts, metrics, links, or features not in the notes.
- Improve transitions between sections so the article flows as a narrative.
- Vary sentence length: mix short punchy sentences with longer explanatory ones.
- Replace passive voice with active voice where possible.
- Cut filler phrases: "It is important to note", "As mentioned above", "In order to", "It should be noted that".
- Cut hedge words when the notes support the claim: "might", "could potentially", "it seems like".
- Replace generic verbs: "utilizes" -> "uses", "leverages" -> "uses" or a more specific verb.
- Ensure every paragraph opens with its key point (inverted pyramid style).
- The closing paragraph must end with a specific call-to-action, not a vague encouragement.
"""
    if strict_mode:
        template += """
- Strict mode: Every sentence must include at least one timestamp citation in the form [t=123.45] that appears in the notes.
"""
    template += """
Notes:
{notes}

Draft:
{draft}
"""
    return PromptTemplate(
        input_variables=["notes", "draft"],
        template=template.strip(),
    )


def _length_guidance(length: str) -> str:
    normalized = (length or "").strip().lower()
    if normalized.startswith("short"):
        return "Short (800-1200 words)"
    if normalized.startswith("long"):
        return "Long (2000-3000 words)"
    return "Medium (1200-2000 words)"


def _length_key(length: str) -> str:
    normalized = (length or "").strip().lower()
    if normalized.startswith("short"):
        return "short"
    if normalized.startswith("long"):
        return "long"
    return "medium"


def _normalize_optional(text: str | None, fallback: str = "Not specified") -> str:
    cleaned = (text or "").strip()
    return cleaned if cleaned else fallback


def _normalize_links(text: str | None) -> str:
    return (text or "").strip()


def _verbosity_guidance(level: str | None) -> str:
    normalized = (level or "").strip().lower()
    if normalized.startswith("concise"):
        return "Concise"
    if normalized.startswith("detail"):
        return "Detailed"
    return "Standard"


def _max_section_sentences(length_key: str, verbosity: str) -> int:
    base_map = {"short": 8, "medium": 12, "long": 16}
    base = base_map.get(length_key, 12)
    if verbosity == "Concise":
        base -= 3
    elif verbosity == "Detailed":
        base += 4
    return max(6, base)


def _length_multiplier(value: int | None) -> int:
    try:
        numeric = int(value) if value is not None else 1
    except (TypeError, ValueError):
        return 1
    return max(1, min(3, numeric))


def _filter_timestamped_lines(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    kept = [line for line in lines if TIMESTAMP_PATTERN.search(line)]
    return "\n".join(kept)


def _normalize_timestamps(text: str) -> str:
    return re.sub(r"\(t=(\d+(?:\.\d+)?)\)", r"[t=\\1]", text)


def _split_line_prefix(line: str) -> tuple[str, str]:
    match = re.match(r"^([\s]*([*+-]|\d+\.)\s+)(.*)$", line)
    if match:
        return match.group(1), match.group(3)
    return "", line


def _split_sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\\s+(?=[A-Z0-9\\[])", text)


def _extract_timestamps(text: str) -> set[str]:
    values: set[str] = set()
    for match in TIMESTAMP_VALUE_PATTERN.finditer(text):
        value = match.group(1) or match.group(2)
        if value:
            values.add(value)
    return values


def _enforce_sentence_timestamps(markdown: str, allowed: set[str]) -> str:
    output_lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            output_lines.append(line)
            continue
        if stripped.startswith("#"):
            output_lines.append(line)
            continue
        if not TIMESTAMP_PATTERN.search(line):
            continue

        prefix, content = _split_line_prefix(line)
        sentences = _split_sentences(content)
        kept: list[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not TIMESTAMP_PATTERN.search(sentence):
                continue
            timestamps = _extract_timestamps(sentence)
            if not timestamps:
                continue
            if timestamps.issubset(allowed):
                kept.append(sentence)
        if not kept:
            continue
        output_lines.append(prefix + " ".join(kept))
    return "\n".join(output_lines).strip()


def _strip_timestamps(text: str) -> str:
    return TIMESTAMP_PATTERN.sub("", text)


def _strip_inline_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    return text


def _normalize_urls(text: str) -> str:
    text = text.replace("hideera.com", "hedera.com")
    text = text.replace("hideera.com/blog", "hedera.com/blog")
    text = text.replace("hedera.comblog", "hedera.com/blog")
    return text


def _normalize_abbreviations(text: str) -> str:
    text = text.replace("Hedera Enhancement Proposals", "Hedera Improvement Proposals")
    text = text.replace("HEPs", "HIPs")
    return text


def _normalize_brand_phrases(text: str) -> str:
    replacements = {
        "Head Starter": "HeadStarter",
        "Head starter": "HeadStarter",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _normalize_markdown_spacing(text: str) -> str:
    # Ensure headings are on their own lines and separated by blank lines.
    text = re.sub(r"(#+ [^\n]+)\s+(- )", r"\1\n\n- ", text)
    text = re.sub(r"(?<!\n)\n(## )", r"\n\n\1", text)
    text = re.sub(r"(#+ [^\n]+)\s+(## )", r"\1\n\n\2", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _collapse_paragraphs(markdown: str) -> str:
    output_lines: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            output_lines.append(" ".join(buffer).strip())
            buffer.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            if output_lines and output_lines[-1] != "":
                output_lines.append("")
            continue
        if stripped.startswith("#") or stripped.startswith("- ") or re.match(r"\\d+\\.\\s+", stripped):
            flush()
            output_lines.append(line)
            continue
        buffer.append(stripped)

    flush()

    cleaned: list[str] = []
    for line in output_lines:
        if line == "" and (not cleaned or cleaned[-1] == ""):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _trim_tldr_bullets(markdown: str, max_bullets: int) -> str:
    sections = _split_h2_sections(markdown)
    if not sections:
        return markdown

    rebuilt: list[str] = []
    for heading, body in sections:
        heading_lower = heading.lower()
        if "tl;dr" not in heading_lower:
            rebuilt.append(heading)
            rebuilt.extend(body)
            continue

        kept: list[str] = []
        bullet_count = 0
        for line in body:
            if line.strip().startswith("- "):
                bullet_count += 1
                if bullet_count > max_bullets:
                    continue
            kept.append(line)
        rebuilt.append(heading)
        rebuilt.extend(kept)

    return "\n".join(rebuilt).strip()


def _markdown_to_plain(markdown: str) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if stripped.startswith("# "):
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(stripped[2:])
            lines.append("")
            continue
        if stripped.startswith("## "):
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(stripped[3:])
            lines.append("")
            continue
        if stripped.startswith("---"):
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if stripped.startswith("- "):
            lines.append(_strip_inline_markdown(stripped))
            continue
        lines.append(_strip_inline_markdown(line))

    cleaned: list[str] = []
    for line in lines:
        if line == "" and (not cleaned or cleaned[-1] == ""):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _extract_proper_tokens(text: str) -> list[str]:
    cleaned = _strip_timestamps(text)
    tokens = PROPER_TOKEN_PATTERN.findall(cleaned)
    return [token for token in tokens if token not in STOPWORDS]


def _build_proper_token_index(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in _extract_proper_tokens(text):
        counts[token] = counts.get(token, 0) + 1
    return counts


def _build_canonical_map(counts: dict[str, int]) -> dict[str, str]:
    from difflib import SequenceMatcher

    items = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    canonical_map: dict[str, str] = {}
    for token, _ in items:
        if token in canonical_map:
            continue
        canonical_map[token] = token
        if len(token) < 4 or token.isupper():
            continue
        for other, _ in items:
            if other == token or other in canonical_map:
                continue
            if other.isupper() or len(other) < 4:
                continue
            similarity = SequenceMatcher(None, token.lower(), other.lower()).ratio()
            if similarity >= 0.88:
                canonical_map[other] = token
    return canonical_map


def _normalize_proper_nouns(markdown: str, canonical_map: dict[str, str]) -> str:
    normalized = markdown
    for token, canonical in canonical_map.items():
        if token == canonical:
            continue
        normalized = re.sub(rf"\\b{re.escape(token)}\\b", canonical, normalized)
    return normalized


def _validate_proper_nouns(
    markdown: str,
    allowed_tokens: set[str],
    canonical_map: dict[str, str],
) -> str:
    output_lines: list[str] = []
    allowed = set(allowed_tokens)
    allowed.update(STOPWORDS)
    allowed.update(canonical_map.values())

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            output_lines.append(line)
            continue

        is_heading = stripped.startswith("#")
        tokens = _extract_proper_tokens(line)
        tokens = [canonical_map.get(token, token) for token in tokens]
        disallowed = [token for token in tokens if token not in allowed]

        if is_heading and disallowed:
            # Replace unsafe headings with a generic, safe one.
            if stripped.startswith("# "):
                output_lines.append("# Hedera Livestream Technical Summary")
            elif stripped.startswith("## "):
                output_lines.append("## Additional details")
            else:
                output_lines.append(line)
            continue

        if is_heading:
            output_lines.append(line)
            continue

        if not tokens:
            output_lines.append(line)
            continue

        if disallowed:
            # Drop sentences with unknown proper nouns.
            prefix, content = _split_line_prefix(line)
            sentences = _split_sentences(content)
            kept: list[str] = []
            for sentence in sentences:
                sentence = sentence.strip()
                sentence_tokens = _extract_proper_tokens(sentence)
                sentence_tokens = [canonical_map.get(token, token) for token in sentence_tokens]
                if any(token not in allowed for token in sentence_tokens):
                    continue
                kept.append(sentence)
            if kept:
                output_lines.append(prefix + " ".join(kept))
            continue

        output_lines.append(line)

    return "\n".join(output_lines).strip()


def _compress_sections(markdown: str, max_sections: int = 5) -> str:
    lines = markdown.splitlines()
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_body: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_heading is not None:
                sections.append((current_heading, current_body))
            else:
                preamble = preamble or []
            current_heading = line
            current_body = []
        else:
            if current_heading is None:
                preamble.append(line)
            else:
                current_body.append(line)

    if current_heading is not None:
        sections.append((current_heading, current_body))

    def is_protected(heading: str) -> bool:
        lower = heading.lower()
        return "tl;dr" in lower or "key takeaways" in lower or "resources" in lower

    non_protected_indices = [i for i, (heading, _) in enumerate(sections) if not is_protected(heading)]
    if len(non_protected_indices) <= max_sections:
        return markdown

    keep_indices = set(non_protected_indices[:max_sections])
    merge_target = non_protected_indices[max_sections - 1]
    merged_sections: list[tuple[str, list[str]]] = []
    index_map: dict[int, int] = {}

    for idx, (heading, body) in enumerate(sections):
        if is_protected(heading) or idx in keep_indices:
            merged_sections.append((heading, body))
            index_map[idx] = len(merged_sections) - 1
            continue

        target_idx = index_map.get(merge_target)
        if target_idx is None:
            continue
        existing_heading, existing_body = merged_sections[target_idx]
        extra_body = [line for line in body if line.strip()]
        if extra_body:
            existing_body.extend([""] + extra_body)
        merged_sections[target_idx] = (existing_heading, existing_body)

    rebuilt: list[str] = []
    rebuilt.extend(preamble)
    for heading, body in merged_sections:
        if rebuilt and rebuilt[-1] != "":
            rebuilt.append("")
        rebuilt.append(heading)
        rebuilt.extend(body)

    return "\n".join(rebuilt).strip()


def _ensure_title(markdown: str, fallback_timestamp: str | None = None) -> str:
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        return markdown
    title = "# Hedera Livestream Technical Summary"
    if fallback_timestamp:
        title = f"{title} [t={fallback_timestamp}]"
    return "\n".join([title, ""] + lines).strip()


def _rename_additional_details(markdown: str) -> str:
    lines: list[str] = []
    count = 0
    for line in markdown.splitlines():
        if line.strip().lower().startswith("## additional details"):
            count += 1
            if count == 1:
                lines.append("## Technical details")
            else:
                lines.append(f"## Technical details {count}")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _auto_label_generic_headings(markdown: str, allowed_tokens: set[str]) -> str:
    sections = _split_h2_sections(markdown)
    if not sections:
        return markdown

    existing_titles = {heading.strip().lower() for heading, _ in sections}
    rebuilt: list[str] = []

    def suggest_heading(body_text: str) -> str:
        lowered = body_text.lower()
        best_score = 0
        best_title = "Hedera ecosystem overview"
        for title, keywords in HEADING_RULES:
            score = sum(1 for keyword in keywords if keyword in lowered)
            if score > best_score:
                best_score = score
                best_title = title
        if best_score == 0:
            candidates = _extract_proper_tokens(body_text)
            candidates = [token for token in candidates if token in allowed_tokens]
            if candidates:
                return " & ".join(candidates[:2]) + " updates"
        return best_title

    for heading, body in sections:
        heading_text = heading[3:].strip()
        heading_lower = heading_text.lower()
        if (
            heading_lower.startswith("technical details")
            or heading_lower == "details"
            or "additional details" in heading_lower
            or heading_lower.endswith("updates")
        ):
            body_text = " ".join(body)
            base = suggest_heading(body_text)

            base_lower = base.lower()
            existing_titles.add(base_lower)
            heading = f"## {base}"

        rebuilt.append(heading)
        rebuilt.extend(body)

    return "\n".join(rebuilt).strip()


def _merge_duplicate_sections(markdown: str) -> str:
    sections = _split_h2_sections(markdown)
    if not sections:
        return markdown

    merged: dict[str, list[str]] = {}
    order: list[str] = []
    for heading, body in sections:
        key = heading.strip().lower()
        if key not in merged:
            merged[key] = [heading] + body
            order.append(key)
        else:
            existing = merged[key]
            extra = [line for line in body if line.strip()]
            if extra:
                existing.extend([""] + extra)
            merged[key] = existing

    rebuilt: list[str] = []
    for key in order:
        rebuilt.extend(merged[key])
    return "\n".join(rebuilt).strip()


def _trim_sections(markdown: str, max_sentences: int) -> str:
    sections = _split_h2_sections(markdown)
    if not sections:
        return markdown

    rebuilt: list[str] = []
    for heading, body in sections:
        heading_lower = heading.lower()
        if "tl;dr" in heading_lower or "key takeaways" in heading_lower or "resources" in heading_lower:
            rebuilt.append(heading)
            rebuilt.extend(body)
            continue

        kept_lines: list[str] = []
        sentence_count = 0
        for line in body:
            if not line.strip():
                kept_lines.append(line)
                continue

            sentences = _split_sentences(line)
            line_sentence_count = sum(1 for sentence in sentences if sentence.strip())
            if sentence_count + line_sentence_count <= max_sentences:
                kept_lines.append(line)
                sentence_count += line_sentence_count
                continue

            remaining = max_sentences - sentence_count
            if remaining > 0:
                prefix, content = _split_line_prefix(line)
                trimmed: list[str] = []
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    trimmed.append(sentence)
                    if len(trimmed) >= remaining:
                        break
                if trimmed:
                    kept_lines.append(prefix + " ".join(trimmed))
                    sentence_count = max_sentences
            break

        while kept_lines and not kept_lines[-1].strip():
            kept_lines.pop()

        rebuilt.append(heading)
        rebuilt.extend(kept_lines)

    return "\n".join(rebuilt).strip()


def _extract_h2_headings(markdown: str) -> list[str]:
    return [line.strip()[3:] for line in markdown.splitlines() if line.startswith("## ")]


def _split_h2_sections(markdown: str) -> list[tuple[str, list[str]]]:
    lines = markdown.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_body: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_heading is not None:
                sections.append((current_heading, current_body))
            current_heading = line.strip()
            current_body = []
        else:
            if current_heading is not None:
                current_body.append(line)

    if current_heading is not None:
        sections.append((current_heading, current_body))

    return sections


def _section_issues(
    markdown: str,
    min_sections: int,
    max_sections: int,
    max_section_sentences: int,
) -> list[str]:
    issues: list[str] = []
    headings = _extract_h2_headings(markdown)
    normalized = [heading.strip().lower() for heading in headings]

    if not any("tl;dr" in heading for heading in normalized):
        issues.append("Missing TL;DR section.")
    if not any("key takeaways" in heading for heading in normalized):
        issues.append("Missing Key takeaways section.")

    generic_headings = [
        heading
        for heading in normalized
        if (
            "additional details" in heading
            or heading.startswith("technical details")
            or heading == "details"
            or heading.endswith("updates")
        )
    ]
    if generic_headings:
        issues.append("Uses generic section headings; replace with descriptive titles.")

    seen: set[str] = set()
    duplicates: set[str] = set()
    for heading in normalized:
        if heading in seen:
            duplicates.add(heading)
        seen.add(heading)
    if duplicates:
        issues.append(f"Duplicate H2 headings: {', '.join(sorted(duplicates))}.")

    content_sections = [
        heading
        for heading in normalized
        if "tl;dr" not in heading and "key takeaways" not in heading and "resources" not in heading
    ]
    if len(content_sections) < min_sections or len(content_sections) > max_sections:
        issues.append(
            f"Needs {min_sections}-{max_sections} content sections; found {len(content_sections)}."
        )

    sections = _split_h2_sections(markdown)
    for heading, body in sections:
        heading_lower = heading.lower()
        if "tl;dr" in heading_lower or "key takeaways" in heading_lower or "resources" in heading_lower:
            continue
        content = " ".join(body)
        sentences = _split_sentences(content)
        sentence_count = sum(1 for sentence in sentences if sentence.strip())
        if sentence_count > max_section_sentences:
            issues.append(
                f"Section '{heading[3:]}' is too long ({sentence_count} sentences); tighten it."
            )

    return issues


def _long_sentence_issues(markdown: str, max_words: int = 35) -> list[str]:
    issues: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        sentences = _split_sentences(stripped)
        for sentence in sentences:
            words = [word for word in sentence.split() if word.strip()]
            if len(words) > max_words:
                issues.append(
                    f"Found a long sentence ({len(words)} words); shorten to ~{max_words}."
                )
                return issues
    return issues


def _strict_sentence_issues(markdown: str) -> list[str]:
    issues: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if "." in stripped or "?" in stripped or "!" in stripped:
            if not TIMESTAMP_PATTERN.search(stripped):
                issues.append("Found a sentence without a timestamp.")
                break
    return issues


def _ensure_api_key() -> str:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set. Add it to your environment or .env file.")
    return api_key


def build_chunk_notes(
    llm: ChatOpenAI,
    chunks: list[str],
    max_chunks: int,
    strict_mode: bool = False,
) -> list[str]:
    """Summarize each chunk into technical notes."""
    notes_prompt = build_notes_prompt(strict_mode=strict_mode)
    notes_chain = LLMChain(llm=llm, prompt=notes_prompt, verbose=False)

    notes: list[str] = []
    for chunk in chunks[:max_chunks]:
        chunk_notes = notes_chain.predict(chunk=chunk).strip()
        if not chunk_notes:
            continue
        if chunk_notes.lower().startswith("no technical details"):
            continue
        if strict_mode:
            chunk_notes = _normalize_timestamps(chunk_notes)
            chunk_notes = _filter_timestamped_lines(chunk_notes)
            if not chunk_notes:
                continue
        notes.append(chunk_notes)
    return notes


def generate_blog_from_notes(
    llm: ChatOpenAI,
    notes: str,
    audience: str,
    length: str,
    focus: str,
    reference_links: str,
    strict_mode: bool = False,
    verbosity: str | None = None,
    length_multiplier: int | None = None,
    auto_iterate: bool = True,
    max_iterations: int = 3,
    min_sections: int = 3,
    max_sections: int = 5,
    include_timestamps: bool = True,
    output_format: str = "Markdown",
    max_section_sentences: int | None = None,
    linguistic_polish: bool = True,
    compliance_check: bool = True,
) -> tuple[str, list[str]]:
    draft_prompt = build_blog_prompt(strict_mode=strict_mode)
    draft_chain = LLMChain(llm=llm, prompt=draft_prompt, verbose=False)
    multiplier = _length_multiplier(length_multiplier)
    draft = draft_chain.predict(
        audience=audience,
        length=length,
        focus=focus,
        reference_links=reference_links,
        notes=notes,
        verbosity=_verbosity_guidance(verbosity),
        length_multiplier=multiplier,
    ).strip()

    review_prompt = build_review_prompt(strict_mode=strict_mode)
    review_chain = LLMChain(llm=llm, prompt=review_prompt, verbose=False)
    review = review_chain.predict(notes=notes, draft=draft).strip()

    publish_prompt = build_publisher_prompt(strict_mode=strict_mode)
    publish_chain = LLMChain(llm=llm, prompt=publish_prompt, verbose=False)
    final = publish_chain.predict(
        audience=audience,
        length=length,
        focus=focus,
        reference_links=reference_links,
        notes=notes,
        review=review,
        verbosity=_verbosity_guidance(verbosity),
        length_multiplier=multiplier,
    ).strip()

    def _postprocess(text: str) -> str:
        processed = text
        if strict_mode:
            processed = _normalize_timestamps(processed)
            allowed = _extract_timestamps(notes)
            processed = _enforce_sentence_timestamps(processed, allowed)
            notes_index = _build_proper_token_index(notes)
            canonical_map = _build_canonical_map(notes_index)
            processed = _normalize_proper_nouns(processed, canonical_map)
            processed = _validate_proper_nouns(processed, set(notes_index.keys()), canonical_map)
            processed = _compress_sections(processed, max_sections=max_sections)
            processed = _rename_additional_details(processed)
            processed = _auto_label_generic_headings(processed, set(notes_index.keys()))
            processed = _merge_duplicate_sections(processed)
            max_sentences = max_section_sentences or 6
            processed = _trim_sections(processed, max_sentences=max_sentences)
            fallback_ts = next(iter(sorted(allowed, key=lambda value: float(value))), None)
            processed = _ensure_title(processed, fallback_timestamp=fallback_ts)
        processed = _normalize_brand_phrases(processed)
        processed = _normalize_abbreviations(processed)
        processed = _normalize_urls(processed)
        processed = _normalize_markdown_spacing(processed)
        processed = _collapse_paragraphs(processed)
        return processed.strip()

    final = _postprocess(final)

    if auto_iterate:
        refine_prompt = build_refine_prompt(strict_mode=strict_mode)
        refine_chain = LLMChain(llm=llm, prompt=refine_prompt, verbose=False)
        for _ in range(max_iterations):
            issues = []
            issues.extend(_section_issues(final, min_sections, max_sections, max_section_sentences or 6))
            if strict_mode:
                issues.extend(_strict_sentence_issues(final))
            issues.extend(_long_sentence_issues(final))
            if not issues:
                break
            final = refine_chain.predict(
                audience=audience,
                length=length,
                focus=focus,
                verbosity=_verbosity_guidance(verbosity),
                length_multiplier=multiplier,
                reference_links=reference_links,
                issues="\n".join(f"- {issue}" for issue in issues),
                notes=notes,
                draft=final,
                min_sections=min_sections,
                max_sections=max_sections,
            ).strip()
            final = _postprocess(final)

    if linguistic_polish:
        linguistic_prompt = build_linguistic_prompt(strict_mode=strict_mode)
        linguistic_chain = LLMChain(llm=llm, prompt=linguistic_prompt, verbose=False)
        final = linguistic_chain.predict(notes=notes, draft=final).strip()
        final = _postprocess(final)

    # --- Compliance check ---
    compliance_warnings: list[str] = []
    if compliance_check:
        from rag.compliance import check_compliance, fix_compliance

        is_compliant, violations = check_compliance(llm, final, notes)
        if not is_compliant:
            final = fix_compliance(llm, final, notes, violations)
            final = _postprocess(final)
            # Re-check after fix
            is_compliant_2, violations_2 = check_compliance(llm, final, notes)
            if not is_compliant_2:
                compliance_warnings = violations_2

    final = final.strip()
    if not include_timestamps:
        final = _strip_timestamps(final)
        final = re.sub(r"[ \t]{2,}", " ", final)
        final = re.sub(r"\n{3,}", "\n\n", final).strip()

    length_key = _length_key(length)
    tldr_max = {"short": 3, "medium": 4, "long": 5}[length_key]
    final = _trim_tldr_bullets(final, tldr_max)

    if output_format.lower().startswith("plain"):
        final = _markdown_to_plain(final)
    return final.strip(), compliance_warnings


def generate_title_suggestions(
    llm: ChatOpenAI,
    blog: str,
    count: int = 5,
) -> str:
    prompt = build_title_prompt()
    chain = LLMChain(llm=llm, prompt=prompt, verbose=False)
    return chain.predict(blog=blog, count=count).strip()


def create_medium_blog_from_youtube(
    video_url: str,
    audience: str,
    length: str,
    focus: str,
    reference_links: str,
    strict_mode: bool = False,
    verbosity: str | None = None,
    length_multiplier: int | None = None,
    auto_iterate: bool = True,
    include_timestamps: bool = True,
    output_format: str = "Markdown",
    linguistic_polish: bool = True,
    enrich_with_docs: bool = True,
    compliance_check: bool = True,
    config: BlogConfig | None = None,
) -> tuple[str, str]:
    """
    Generate a Medium-ready technical blog post about a Hedera livestream.

    Returns:
        tuple[str, str]: (blog_output, status_message)
    """
    config = config or BlogConfig()

    video_id = extract_video_id(video_url)
    if not video_id:
        return "", "Please provide a valid YouTube video URL or ID."

    transcript, error = fetch_transcript(video_id)
    if error:
        return "", error

    transcript_text = format_transcript(transcript, include_timestamps=strict_mode)
    if not transcript_text:
        return "", "Transcript was found, but it contained no usable text."

    _ensure_api_key()
    length_key = _length_key(length)
    verbosity_key = _verbosity_guidance(verbosity)
    max_sentences = _max_section_sentences(length_key, verbosity_key)
    max_sections = min(config.max_sections, {"short": 2, "medium": 3, "long": 4}[length_key])
    min_sections = min(config.min_sections, max_sections)
    llm = ChatOpenAI(
        model=config.model_name,
        temperature=config.temperature,
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    chunks = split_text(
        transcript_text,
        chunk_size=config.notes_chunk_size,
        chunk_overlap=config.notes_chunk_overlap,
    )

    notes_list = build_chunk_notes(llm, chunks, config.max_chunks, strict_mode=strict_mode)
    if not notes_list:
        return "", "No technical details were detected in the transcript."

    notes = "\n\n".join(notes_list)

    # --- Enrich notes with official Hedera documentation ---
    docs_status = ""
    if enrich_with_docs:
        try:
            from rag.hedera_docs import get_relevant_context

            docs_context, num_chunks, docs_errors = get_relevant_context(notes, k=5)
            if docs_context:
                notes = (
                    notes
                    + "\n\n--- Official Hedera Documentation Context ---\n\n"
                    + docs_context
                )
                docs_status = f"Docs enrichment: {num_chunks} chunks retrieved. "
            else:
                docs_status = "Docs enrichment: no relevant docs found. "
            if docs_errors:
                docs_status += f"Docs warnings: {len(docs_errors)}. "
        except Exception as exc:
            docs_status = f"Docs enrichment failed: {exc}. "

    blog, compliance_warnings = generate_blog_from_notes(
        llm,
        notes,
        audience=_normalize_optional(audience, "Web3 developers and Hedera builders"),
        length=_length_guidance(length),
        focus=_normalize_optional(focus, "Not specified"),
        reference_links=_normalize_links(reference_links),
        strict_mode=strict_mode,
        verbosity=verbosity,
        length_multiplier=length_multiplier,
        auto_iterate=auto_iterate,
        max_iterations=config.max_iterations,
        min_sections=min_sections,
        max_sections=max_sections,
        include_timestamps=include_timestamps,
        output_format=output_format,
        max_section_sentences=max_sentences,
        linguistic_polish=linguistic_polish,
        compliance_check=compliance_check,
    )

    # --- Build status ---
    compliance_status = "Compliance: PASS. " if not compliance_warnings else (
        f"Compliance: {len(compliance_warnings)} warning(s). "
    )

    status = (
        f"Transcript lines: {len(transcript_text.splitlines())}. "
        f"Notes chunks summarized: {min(len(chunks), config.max_chunks)}. "
        f"{docs_status}"
        f"{compliance_status}"
        f"Strict mode: {'on' if strict_mode else 'off'}. "
        f"Verbosity: {_verbosity_guidance(verbosity)}. "
        f"Length multiplier: {_length_multiplier(length_multiplier)}. "
        f"Auto-iterate: {'on' if auto_iterate else 'off'}. "
        f"Timestamps in output: {'on' if include_timestamps else 'off'}. "
        f"Format: {output_format}. "
        f"Max sections: {max_sections}. "
        f"Max sentences/section: {max_sentences}. "
        f"Linguistic polish: {'on' if linguistic_polish else 'off'}."
    )
    return blog.strip(), status


def create_medium_blog_with_titles(
    video_url: str,
    audience: str,
    length: str,
    focus: str,
    reference_links: str,
    strict_mode: bool = False,
    verbosity: str | None = None,
    length_multiplier: int | None = None,
    auto_iterate: bool = True,
    include_timestamps: bool = True,
    output_format: str = "Markdown",
    linguistic_polish: bool = True,
    enrich_with_docs: bool = True,
    compliance_check: bool = True,
    titles_count: int = 5,
    config: BlogConfig | None = None,
) -> tuple[str, str, str]:
    blog, status = create_medium_blog_from_youtube(
        video_url=video_url,
        audience=audience,
        length=length,
        focus=focus,
        reference_links=reference_links,
        strict_mode=strict_mode,
        verbosity=verbosity,
        length_multiplier=length_multiplier,
        auto_iterate=auto_iterate,
        include_timestamps=include_timestamps,
        output_format=output_format,
        linguistic_polish=linguistic_polish,
        enrich_with_docs=enrich_with_docs,
        compliance_check=compliance_check,
        config=config,
    )

    if not blog:
        return "", "", status

    config = config or BlogConfig()
    _ensure_api_key()
    llm = ChatOpenAI(
        model=config.model_name,
        temperature=config.temperature,
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    titles = generate_title_suggestions(llm, blog, count=titles_count)
    return blog, titles, status
