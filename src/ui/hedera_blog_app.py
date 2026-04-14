"""Gradio UI for generating Hedera Medium-ready technical blogs from YouTube livestreams."""

from __future__ import annotations

import os
import webbrowser

import gradio as gr

from rag.hedera_blog import extract_video_id, fetch_transcript, format_transcript
from rag.compliance import COMPLIANCE_GPT_URL
from rag.youtube_search import fetch_hedera_livestreams
from crew.crew import ContentBlogCrew


# Cache to map dropdown labels back to URLs
_livestream_cache: dict[str, str] = {}


def load_livestreams() -> gr.Dropdown:
    """Fetch the last 10 Hedera livestreams and populate the dropdown."""
    results, error = fetch_hedera_livestreams(limit=10)
    if error:
        gr.Warning(error)
        return gr.Dropdown(choices=[], value=None)

    _livestream_cache.clear()
    choices = []
    for item in results:
        label = f"{item['title']}  \u2014  {item['url']}"
        _livestream_cache[label] = item["url"]
        choices.append(label)

    return gr.Dropdown(choices=choices, value=choices[0] if choices else None)


def open_compliance_gpt() -> str:
    """Open the Hedera Content Compliance GPT in the browser."""
    webbrowser.open(COMPLIANCE_GPT_URL)
    return f"Opened: {COMPLIANCE_GPT_URL}"


def generate_blog(
    selected_livestream: str | None,
    manual_url: str,
    audience: str,
    focus: str,
    reference_links: str,
    enrich_with_docs: bool,
    compliance_check: bool,
    auto_publish: bool,
    model_choice: str,
    custom_model: str,
    output_format: str,
    titles_count: int,
) -> tuple[str, str, str]:
    # Resolve video URL
    video_url = (manual_url or "").strip()
    if not video_url and selected_livestream:
        video_url = _livestream_cache.get(selected_livestream, selected_livestream)

    if not video_url:
        return "", "", "Please select a livestream or enter a URL."

    # Set model via env var for CrewAI
    selected_model = (custom_model or "").strip() or model_choice
    if selected_model:
        os.environ["OPENAI_MODEL"] = selected_model

    # Extract transcript
    video_id = extract_video_id(video_url)
    if not video_id:
        return "", "", "Invalid YouTube URL or video ID."

    transcript, error = fetch_transcript(video_id)
    if error:
        return "", "", error

    transcript_text = format_transcript(transcript, include_timestamps=False)
    if not transcript_text:
        return "", "", "Transcript was found but contained no usable text."

    # Run the multi-agent crew
    try:
        crew = ContentBlogCrew(
            include_docs=enrich_with_docs,
            include_compliance=compliance_check,
        )
        result = crew.run(
            transcript_text=transcript_text,
            audience=audience,
            focus=focus,
            reference_links=reference_links,
            titles_count=int(titles_count),
            output_format=output_format,
        )
        blog = result["blog"]
        titles = result["titles"]
        tags = result.get("tags", [])
        status = result["status"]

        # Append tags to the titles output for visibility in the UI
        if tags:
            titles = titles + "\n\n--- Tags ---\n" + "\n".join(tags)

        # Auto-publish to GitHub Pages
        if auto_publish and blog:
            try:
                from rag.publisher import publish_to_github_pages
                url, pub_error = publish_to_github_pages(
                    blog,
                    focus=focus,
                    tags=tags,
                )
                if url:
                    status += f" | Published: {url}"
                elif pub_error:
                    status += f" | Publish failed: {pub_error}"
            except Exception as pub_exc:
                status += f" | Publish error: {pub_exc}"

        return blog, titles, status
    except Exception as exc:  # noqa: BLE001 - surface to UI
        return "", "", f"Error: {exc}"


def build_app() -> gr.Blocks:
    with gr.Blocks() as app:
        gr.Markdown(
            """
# Hedera Livestream \u2192 Medium Technical Blog
Pick a recent Hedera livestream (or paste a URL) and get a publish-ready technical blog.

**Multi-agent pipeline**: Transcript Researcher \u2192 Docs Researcher \u2192 Technical Writer \u2192 Editor \u2192 Compliance Reviewer \u2192 Publisher
"""
        )

        # --- Livestream picker ---
        with gr.Row():
            fetch_btn = gr.Button("Fetch Last 10 Livestreams", variant="secondary")

        livestream_dropdown = gr.Dropdown(
            label="Select a Hedera Livestream",
            choices=[],
            interactive=True,
        )

        manual_url = gr.Textbox(
            label="Or enter a YouTube URL manually",
            placeholder="https://www.youtube.com/watch?v=VIDEO_ID",
        )

        fetch_btn.click(
            fn=load_livestreams,
            inputs=[],
            outputs=[livestream_dropdown],
        )

        # --- Blog settings ---
        with gr.Row():
            audience = gr.Textbox(
                label="Target audience",
                value="Web3 developers and Hedera builders",
            )
            focus = gr.Textbox(
                label="Focus areas (optional)",
                placeholder="e.g., Hashgraph consensus, HCS, HTS, EVM tooling",
            )

        reference_links = gr.Textbox(
            label="Reference links (optional, one per line)",
            placeholder="Paste any official links you want included in a Resources section",
            lines=3,
        )

        # --- RAG, Compliance & Publish toggles ---
        with gr.Row():
            enrich_with_docs = gr.Checkbox(
                label="Enrich with official Hedera docs",
                value=True,
            )
            compliance_check = gr.Checkbox(
                label="Auto-check compliance",
                value=True,
            )
            auto_publish = gr.Checkbox(
                label="Auto-publish to GitHub Pages",
                value=True,
            )

        with gr.Accordion("Advanced settings", open=False):
            model_choice = gr.Dropdown(
                choices=[
                    "gpt-4o-mini",
                    "gpt-4o",
                    "gpt-4.1-mini",
                    "gpt-4.1",
                    "gpt-5-mini",
                    "gpt-5",
                    "gpt-5-nano",
                ],
                value="gpt-5-mini",
                label="Model",
            )
            custom_model = gr.Textbox(
                label="Custom model (optional)",
                placeholder="Override the dropdown if needed",
            )
            output_format = gr.Radio(
                choices=["Markdown", "Plain text"],
                value="Markdown",
                label="Output format",
            )
            titles_count = gr.Slider(
                3,
                7,
                value=5,
                step=1,
                label="Title suggestions count",
            )

        generate_btn = gr.Button("Generate Medium Blog", variant="primary")

        blog_output = gr.Textbox(
            label="Medium-ready blog (Markdown)",
            lines=28,
            show_copy_button=True,
        )
        titles_output = gr.Textbox(
            label="Title suggestions",
            lines=6,
            show_copy_button=True,
        )
        status_output = gr.Textbox(label="Status", interactive=False)

        # --- Compliance manual review button ---
        with gr.Row():
            compliance_btn = gr.Button(
                "Open Hedera Compliance GPT (manual review)",
                variant="secondary",
            )
            compliance_status = gr.Textbox(
                label="",
                interactive=False,
                visible=True,
                scale=2,
            )

        compliance_btn.click(
            fn=open_compliance_gpt,
            inputs=[],
            outputs=[compliance_status],
        )

        generate_btn.click(
            generate_blog,
            inputs=[
                livestream_dropdown,
                manual_url,
                audience,
                focus,
                reference_links,
                enrich_with_docs,
                compliance_check,
                auto_publish,
                model_choice,
                custom_model,
                output_format,
                titles_count,
            ],
            outputs=[blog_output, titles_output, status_output],
        )

    return app


if __name__ == "__main__":
    build_app().launch(server_name="0.0.0.0", server_port=None)
