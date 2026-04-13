# HederaContentCreatorHelper

Generate Medium-ready technical blog posts from Hedera YouTube livestream transcripts.

## What it does

1. Extracts the transcript from a YouTube video (livestream or regular)
2. Chunks the transcript and summarizes each chunk into technical notes
3. Generates a Medium-ready blog draft using a multi-step LLM pipeline:
   - Draft generation
   - Fact-checking review against the notes
   - Final publisher pass
   - Auto-iteration to fix structural issues
   - Linguistic polish pass
4. Suggests title options for the blog

## Features

- **Strict mode**: Every claim must include a timestamp citation from the transcript
- **Auto-iterate**: Automatically refines the draft until structural quality checks pass
- **Configurable verbosity**: Concise, Standard, or Detailed output
- **Length control**: Short, Medium, or Long blog output with a multiplier
- **Output format**: Markdown or Plain text
- **Title suggestions**: Generates multiple title options based on the final blog

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `config/.env.example` to `.env` and add your OpenAI API key:

```bash
cp config/.env.example .env
```

## Usage

### Gradio UI

```bash
PYTHONPATH=src python -m ui.app
```

Or use the launcher script:

```bash
./run.sh
```

### Programmatic

```python
from rag.hedera_blog import create_medium_blog_with_titles

blog, titles, status = create_medium_blog_with_titles(
    video_url="https://www.youtube.com/watch?v=VIDEO_ID",
    audience="Web3 developers and Hedera builders",
    length="Medium",
    focus="Hedera native services, tooling",
    reference_links="",
    strict_mode=True,
    verbosity="Standard",
    auto_iterate=True,
)
```

## Testing

```bash
# Unit tests
pytest

# Live integration test (requires API key)
OPENAI_API_KEY=sk-... RUN_LIVE_TESTS=1 pytest tests/rag/test_publishable_blog.py -m slow
```

## Project Structure

```
HederaContentCreatorHelper/
├── config/
│   └── .env.example
├── src/
│   ├── rag/
│   │   └── hedera_blog.py      # Core blog generation engine
│   └── ui/
│       ├── app.py               # UI entrypoint
│       └── hedera_blog_app.py   # Gradio interface
├── tests/
│   └── rag/
│       └── test_publishable_blog.py
├── requirements.txt
├── run.sh
└── README.md
```
