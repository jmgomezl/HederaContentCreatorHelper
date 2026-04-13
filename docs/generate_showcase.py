"""Generate a PDF showcase and architecture diagram for HederaContentCreatorHelper."""

from fpdf import FPDF


class ShowcasePDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(130, 89, 239)  # Hedera purple
        self.cell(0, 8, "HederaContentCreatorHelper", align="R")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(40, 40, 40)
        self.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(130, 89, 239)
        self.set_line_width(0.8)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def body_text(self, text):
        self.set_font("Helvetica", "", 11)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 6, text)
        self.ln(3)

    def bullet(self, text):
        self.set_font("Helvetica", "", 11)
        self.set_text_color(50, 50, 50)
        x = self.get_x()
        self.cell(6, 6, "-")
        self.multi_cell(0, 6, text)
        self.ln(1)

    def code_block(self, text):
        self.set_font("Courier", "", 9)
        self.set_fill_color(240, 240, 245)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5, text, fill=True)
        self.ln(3)

    def feature_box(self, title, description):
        self.set_fill_color(245, 242, 255)  # Light purple
        self.set_draw_color(130, 89, 239)
        y_start = self.get_y()
        self.rect(10, y_start, 190, 22, style="DF")
        self.set_xy(14, y_start + 2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(80, 50, 160)
        self.cell(0, 6, title, new_x="LMARGIN", new_y="NEXT")
        self.set_x(14)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(60, 60, 60)
        self.cell(0, 6, description, new_x="LMARGIN", new_y="NEXT")
        self.set_y(y_start + 25)


def create_pdf(output_path):
    pdf = ShowcasePDF()
    pdf.alias_nb_pages()

    # ──── PAGE 1: Title ────
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font("Helvetica", "B", 32)
    pdf.set_text_color(130, 89, 239)
    pdf.cell(0, 15, "HederaContentCreator", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 15, "Helper", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, "YouTube Livestream to Medium Technical Blog", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "with RAG Enrichment & Compliance Checking", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)
    pdf.set_font("Helvetica", "I", 11)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 8, "Powered by LangChain, FAISS, OpenAI, and Gradio", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Built for the Hedera developer community", align="C", new_x="LMARGIN", new_y="NEXT")

    # ──── PAGE 2: What It Does ────
    pdf.add_page()
    pdf.section_title("What It Does")
    pdf.body_text(
        "HederaContentCreatorHelper transforms Hedera YouTube livestreams into "
        "publish-ready Medium technical blog posts. It automates the entire content "
        "pipeline: transcript extraction, technical note-taking, blog drafting, "
        "fact-checking, compliance verification, and linguistic polishing."
    )
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 8, "The Pipeline", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    steps = [
        ("1. Fetch Livestreams", "Pulls the last 10 Hedera livestreams from YouTube via scrapetube"),
        ("2. Extract Transcript", "Downloads and processes the English transcript with timestamps"),
        ("3. Build Technical Notes", "Chunks the transcript and summarizes each chunk into technical notes (12 LLM calls)"),
        ("4. Enrich with Hedera Docs", "Scrapes docs.hedera.com, hedera.com/blog, and hedera.com/learning, builds a FAISS index, retrieves relevant context"),
        ("5. Generate Draft", "Multi-step LLM pipeline: Draft -> Review -> Publisher pass"),
        ("6. Auto-Iterate", "Checks for structural issues and refines automatically (up to 2 rounds)"),
        ("7. Linguistic Polish", "Professional editing pass: cuts filler, improves flow, active voice"),
        ("8. Compliance Check", "Validates against Hedera brand guidelines, fixes violations automatically"),
        ("9. Title Suggestions", "Generates 5 compelling title options"),
    ]
    for title, desc in steps:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(130, 89, 239)
        pdf.cell(50, 6, title)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(0, 6, desc, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    # ──── PAGE 3: Key Features ────
    pdf.add_page()
    pdf.section_title("Key Features")
    pdf.ln(2)

    features = [
        ("Livestream Picker", "Fetches the last 10 Hedera livestreams  - no URL copy-pasting needed."),
        ("RAG Doc Enrichment", "Scrapes 3 official Hedera sources and builds a FAISS vector index for context retrieval."),
        ("Hedera Compliance", "Auto-checks terminology, branding, technical accuracy per Hedera guidelines."),
        ("Multi-Step LLM Pipeline", "Draft -> Review -> Publish -> Iterate -> Polish  - not a single-shot generation."),
        ("Compliance GPT Integration", "One-click button to open the official Hedera Content Compliance GPT for manual review."),
        ("Cost Optimized", "Defaults to gpt-5-mini (~$0.10/blog) with 12 chunks and 2 iterations."),
    ]
    for title, desc in features:
        pdf.feature_box(title, desc)

    # ──── PAGE 4: Architecture ────
    pdf.add_page()
    pdf.section_title("Architecture Diagram")
    pdf.ln(2)
    pdf.set_font("Courier", "", 8)
    pdf.set_fill_color(245, 245, 250)
    arch = """
+---------------------------+     +---------------------------+
|     GRADIO UI (7860)      |     |    HEDERA DOCS RAG        |
|  - Livestream Picker      |     |  - docs.hedera.com        |
|  - Settings & Toggles     |     |  - hedera.com/blog        |
|  - Blog Output + Copy     |     |  - hedera.com/learning    |
|  - Compliance GPT Button  |     |  - FAISS Vector Store     |
+------------+--------------+     +------------+--------------+
             |                                  |
             v                                  v
+----------------------------------------------------------+
|                 BLOG GENERATION PIPELINE                  |
|                                                          |
|  YouTube URL -> Transcript -> Chunk Notes (x12 LLM)      |
|       |                                                  |
|       +-- Enrich notes with FAISS doc retrieval          |
|       |                                                  |
|       v                                                  |
|  Draft (LLM) -> Review (LLM) -> Publisher (LLM)         |
|       |                                                  |
|       +-- Auto-Iterate Loop (max 2 rounds)               |
|       |     - Structural checks                          |
|       |     - Refine chain                               |
|       |                                                  |
|       +-- Linguistic Polish (LLM)                        |
|       |                                                  |
|       +-- Compliance Check (LLM)                         |
|       |     - Terminology & branding                     |
|       |     - Technical accuracy                         |
|       |     - Auto-fix violations                        |
|       |                                                  |
|       v                                                  |
|  Title Suggestions (LLM) -> Final Output                 |
+----------------------------------------------------------+
             |
             v
+----------------------------------------------------------+
|                     EXTERNAL SERVICES                     |
|  - OpenAI API (gpt-5-mini, text-embedding-3-small)       |
|  - YouTube Transcript API                                |
|  - scrapetube (channel listing)                          |
|  - Hedera Content Compliance GPT (manual review)         |
+----------------------------------------------------------+
"""
    pdf.multi_cell(0, 4, arch.strip(), fill=True)

    # ──── PAGE 5: Project Structure ────
    pdf.add_page()
    pdf.section_title("Project Structure")
    pdf.ln(2)
    pdf.code_block(
        "HederaContentCreatorHelper/\n"
        "+-- src/\n"
        "|   +-- rag/\n"
        "|   |   +-- hedera_blog.py      # Core blog generation engine\n"
        "|   |   +-- hedera_docs.py      # Hedera docs scraper + FAISS RAG\n"
        "|   |   +-- compliance.py       # Compliance check chain\n"
        "|   |   +-- youtube_search.py   # Livestream fetcher\n"
        "|   +-- ui/\n"
        "|       +-- app.py              # Entrypoint\n"
        "|       +-- hedera_blog_app.py  # Gradio dashboard\n"
        "+-- tests/\n"
        "|   +-- test_config.py          # 34 unit tests\n"
        "|   +-- rag/\n"
        "|       +-- test_publishable_blog.py  # Integration test\n"
        "+-- config/\n"
        "|   +-- .env.example\n"
        "+-- requirements.txt\n"
        "+-- run.sh\n"
        "+-- README.md"
    )

    pdf.ln(4)
    pdf.section_title("Cost Estimate")
    pdf.ln(2)

    # Table header
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(130, 89, 239)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(60, 8, "Model", border=1, fill=True, align="C")
    pdf.cell(40, 8, "Cost/Blog", border=1, fill=True, align="C")
    pdf.cell(45, 8, "Est. Time", border=1, fill=True, align="C")
    pdf.cell(45, 8, "Quality", border=1, fill=True, align="C")
    pdf.ln()

    # Table rows
    rows = [
        ("gpt-5-mini (default)", "$0.10", "5-8 min", "Very good"),
        ("gpt-4.1-mini", "$0.08", "5-7 min", "Good"),
        ("gpt-4.1", "$0.15", "8-12 min", "Very good"),
        ("gpt-5.1", "$0.60", "20-30 min", "Excellent"),
    ]
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    for i, (model, cost, time, quality) in enumerate(rows):
        fill = i == 0
        if fill:
            pdf.set_fill_color(245, 242, 255)
        pdf.cell(60, 7, model, border=1, fill=fill, align="C")
        pdf.cell(40, 7, cost, border=1, fill=fill, align="C")
        pdf.cell(45, 7, time, border=1, fill=fill, align="C")
        pdf.cell(45, 7, quality, border=1, fill=fill, align="C")
        pdf.ln()

    # ──── PAGE 6: Compliance Rules ────
    pdf.add_page()
    pdf.section_title("Hedera Compliance Rules (Auto-Enforced)")
    pdf.ln(2)

    rules = [
        ("Terminology", 'Brand name is "Hedera" (not "Hedera Hashgraph"). Native token is "HBAR". Uses "hashgraph consensus", not "blockchain".'),
        ("Services", "Official names: Hedera Token Service (HTS), Hedera Consensus Service (HCS), Hedera Smart Contract Service."),
        ("Technical", "Finality in 3-5 seconds (not instant). aBFT consensus. Don't claim fastest/most secure without qualification."),
        ("Prohibited", "No investment advice. No price predictions. No unverified partnerships. No hype language."),
        ("Brand Names", 'HIPs (not HEPs). HeadStarter (not Head Starter). Swirlds Labs (not Swirls).'),
        ("Tone", "Professional, builder-focused, factual. Every claim traceable to transcript or official docs."),
    ]
    for title, desc in rules:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(130, 89, 239)
        pdf.cell(30, 7, title)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 6, desc)
        pdf.ln(2)

    # ──── PAGE 7: Quick Start ────
    pdf.add_page()
    pdf.section_title("Quick Start")
    pdf.ln(2)
    pdf.body_text("1. Setup:")
    pdf.code_block(
        "cd HederaContentCreatorHelper\n"
        "python3 -m venv .venv && source .venv/bin/activate\n"
        "pip install -r requirements.txt\n"
        "cp config/.env.example .env  # Add your OPENAI_API_KEY"
    )
    pdf.body_text("2. Run the dashboard:")
    pdf.code_block("./run.sh")
    pdf.body_text("3. Open http://127.0.0.1:7860 in your browser")
    pdf.ln(4)
    pdf.body_text("4. Workflow:")
    pdf.bullet('Click "Fetch Last 10 Livestreams"')
    pdf.bullet("Select a livestream from the dropdown")
    pdf.bullet('Click "Generate Medium Blog"')
    pdf.bullet("Wait ~5-8 minutes for the pipeline to complete")
    pdf.bullet("Copy the Markdown output and paste into Medium")
    pdf.bullet('Optionally click "Open Hedera Compliance GPT" for manual final review')

    pdf.ln(8)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(130, 89, 239)
    pdf.cell(0, 8, "Run tests:", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block("PYTHONPATH=src pytest tests/test_config.py -v\n# 34 tests, all passing")

    pdf.output(output_path)
    print(f"PDF created: {output_path}")


if __name__ == "__main__":
    create_pdf("docs/HederaContentCreatorHelper_Showcase.pdf")
