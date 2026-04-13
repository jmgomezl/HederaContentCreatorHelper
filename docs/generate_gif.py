"""Generate an animated GIF showcasing the HederaContentCreatorHelper workflow."""

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 900, 600
BG_COLOR = (18, 18, 24)
HEDERA_PURPLE = (130, 89, 239)
HEDERA_LIGHT = (180, 150, 255)
WHITE = (255, 255, 255)
GRAY = (160, 160, 170)
DARK_GRAY = (40, 40, 50)
GREEN = (80, 200, 120)
CARD_BG = (28, 28, 38)


def get_font(size, bold=False):
    try:
        if bold:
            return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size, index=1)
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size, index=0)
    except Exception:
        return ImageFont.load_default()


def draw_header(draw):
    draw.rectangle([(0, 0), (WIDTH, 50)], fill=(25, 25, 35))
    font = get_font(18, bold=True)
    draw.text((20, 14), "HederaContentCreatorHelper", fill=HEDERA_PURPLE, font=font)
    small = get_font(12)
    draw.text((620, 18), "http://127.0.0.1:7860", fill=GRAY, font=small)


def draw_progress_bar(draw, y, progress, label):
    bar_x, bar_w, bar_h = 60, 780, 20
    draw.rectangle([(bar_x, y), (bar_x + bar_w, y + bar_h)], fill=DARK_GRAY, outline=(50, 50, 60))
    fill_w = int(bar_w * progress)
    if fill_w > 0:
        draw.rectangle([(bar_x, y), (bar_x + fill_w, y + bar_h)], fill=HEDERA_PURPLE)
    font = get_font(11)
    draw.text((bar_x + bar_w // 2 - 60, y + 3), label, fill=WHITE, font=font)


def make_frame_title():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    big = get_font(36, bold=True)
    med = get_font(18)
    small = get_font(14)
    draw.text((WIDTH // 2 - 280, 160), "HederaContentCreatorHelper", fill=HEDERA_PURPLE, font=big)
    draw.text((WIDTH // 2 - 220, 230), "YouTube Livestream -> Medium Blog", fill=WHITE, font=med)
    draw.text((WIDTH // 2 - 200, 280), "RAG Enrichment  |  Compliance Check", fill=HEDERA_LIGHT, font=small)
    draw.text((WIDTH // 2 - 130, 340), "Powered by LangChain + FAISS", fill=GRAY, font=small)
    # Decorative line
    draw.line([(200, 310), (700, 310)], fill=HEDERA_PURPLE, width=2)
    return img


def make_frame_fetch():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_header(draw)
    font = get_font(14, bold=True)
    small = get_font(12)

    # Button
    draw.rounded_rectangle([(30, 70), (250, 100)], radius=6, fill=HEDERA_PURPLE)
    draw.text((45, 76), "Fetch Last 10 Livestreams", fill=WHITE, font=small)

    # Dropdown with results
    draw.rounded_rectangle([(30, 115), (870, 145)], radius=6, fill=CARD_BG, outline=(60, 60, 70))
    draw.text((40, 121), "Select a Hedera Livestream", fill=GRAY, font=small)

    livestreams = [
        "Fork-testing Hedera Smart Contracts",
        "Building real-world utility",
        "Deploying Smart Contracts with Native On-Chain Automation",
        "Delivering Trust in Environmental Assets with Hedera Guardian",
        "Building AI Agents on Bonzo Finance",
    ]
    y = 155
    for i, title in enumerate(livestreams):
        bg = (35, 35, 50) if i % 2 == 0 else (30, 30, 42)
        draw.rectangle([(30, y), (870, y + 28)], fill=bg)
        marker = "> " if i == 0 else "  "
        color = HEDERA_LIGHT if i == 0 else GRAY
        draw.text((40, y + 6), f"{marker}{title}", fill=color, font=small)
        y += 30

    # Arrow pointing to selected
    draw.text((40, y + 15), "Selected: Fork-testing Hedera Smart Contracts", fill=GREEN, font=font)

    return img


def make_frame_settings():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_header(draw)
    font = get_font(14, bold=True)
    small = get_font(12)

    draw.text((30, 65), "Configuration", fill=WHITE, font=font)

    settings = [
        ("Target audience:", "Web3 developers and Hedera builders", True),
        ("Focus areas:", "Hashgraph consensus, HCS, HTS, EVM tooling", True),
        ("Enrich with Hedera docs:", "ON", True),
        ("Auto-check compliance:", "ON", True),
        ("Model:", "gpt-5-mini", True),
        ("Max chunks:", "12", True),
        ("Max iterations:", "2", True),
    ]
    y = 100
    for label, value, checked in settings:
        draw.text((50, y), label, fill=GRAY, font=small)
        color = GREEN if value == "ON" else HEDERA_LIGHT
        draw.text((280, y), value, fill=color, font=small)
        y += 35

    # Generate button
    draw.rounded_rectangle([(30, y + 20), (870, y + 60)], radius=8, fill=HEDERA_PURPLE)
    btn_font = get_font(16, bold=True)
    draw.text((350, y + 30), "Generate Medium Blog", fill=WHITE, font=btn_font)

    return img


def make_frame_pipeline(step, total_steps=9):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_header(draw)
    font = get_font(14, bold=True)
    small = get_font(12)

    steps = [
        ("Extracting transcript...", 0.1),
        ("Building technical notes (12 chunks)...", 0.25),
        ("Fetching Hedera docs (docs, blog, learning)...", 0.35),
        ("Building FAISS index...", 0.45),
        ("Generating blog draft...", 0.55),
        ("Review & fact-checking...", 0.65),
        ("Publisher pass...", 0.72),
        ("Auto-iterating (round 1/2)...", 0.80),
        ("Linguistic polish...", 0.85),
        ("Compliance check...", 0.90),
        ("Generating title suggestions...", 0.95),
        ("Done!", 1.0),
    ]

    current = steps[min(step, len(steps) - 1)]
    draw.text((30, 65), "Generating blog...", fill=WHITE, font=font)
    draw_progress_bar(draw, 100, current[1], current[0])

    # Show completed steps
    y = 150
    for i in range(min(step + 1, len(steps))):
        color = GREEN if i < step else HEDERA_LIGHT
        icon = "[done]" if i < step else "[....]"
        draw.text((50, y), f"{icon}  {steps[i][0]}", fill=color, font=small)
        y += 25
        if y > 550:
            break

    return img


def make_frame_output():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_header(draw)
    font = get_font(14, bold=True)
    small = get_font(11)
    tiny = get_font(10)

    draw.text((30, 60), "Medium-ready blog (Markdown)", fill=WHITE, font=font)
    draw.rounded_rectangle([(30, 85), (870, 380)], radius=6, fill=CARD_BG, outline=(60, 60, 70))

    blog_lines = [
        "# Fork-Testing Hedera Smart Contracts: A Developer's Guide",
        "",
        "*How to snapshot mainnet state and run deterministic tests*",
        "*without spending gas*",
        "",
        "The April technical call introduced the Hedera Forking",
        "Library, a tool that lets you snapshot a live block and",
        "test against real contracts, balances, and liquidity...",
        "",
        "## TL;DR",
        "- Fork any Hedera block for local deterministic testing",
        "- Foundry deploys emulation contracts at system addresses",
        "- Hardhat intercepts JSON-RPC calls transparently",
        "- HTS precompile at 0x167 is fully emulated",
        "",
        "## How the Forking Library Simulates Mainnet State",
        "...",
    ]
    y = 92
    for line in blog_lines:
        if line.startswith("# "):
            draw.text((40, y), line, fill=HEDERA_LIGHT, font=font)
        elif line.startswith("## "):
            draw.text((40, y), line, fill=HEDERA_PURPLE, font=small)
        elif line.startswith("*"):
            draw.text((40, y), line, fill=GRAY, font=tiny)
        elif line.startswith("- "):
            draw.text((40, y), line, fill=WHITE, font=tiny)
        elif line:
            draw.text((40, y), line, fill=(200, 200, 210), font=tiny)
        y += 16

    # Title suggestions
    draw.text((30, 395), "Title suggestions", fill=WHITE, font=font)
    draw.rounded_rectangle([(30, 415), (870, 500)], radius=6, fill=CARD_BG, outline=(60, 60, 70))
    titles = [
        "1. Fork-Testing Hedera Smart Contracts: A Developer's Guide",
        "2. How to Test DeFi on Hedera Without Spending Gas",
        "3. The Hedera Forking Library: Mainnet Testing Made Local",
    ]
    y = 425
    for t in titles:
        draw.text((40, y), t, fill=HEDERA_LIGHT, font=tiny)
        y += 22

    # Status
    draw.text((30, 515), "Status: Compliance: PASS | Docs enrichment: 5 chunks | 12 notes chunks", fill=GREEN, font=small)

    # Compliance GPT button
    draw.rounded_rectangle([(30, 545), (350, 575)], radius=6, fill=(50, 50, 65), outline=HEDERA_PURPLE)
    draw.text((45, 552), "Open Hedera Compliance GPT", fill=HEDERA_LIGHT, font=small)

    return img


def make_frame_end():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    big = get_font(28, bold=True)
    med = get_font(16)
    small = get_font(13)

    draw.text((WIDTH // 2 - 180, 180), "Blog Ready to Publish!", fill=GREEN, font=big)
    draw.line([(250, 225), (650, 225)], fill=GREEN, width=2)

    stats = [
        "Model: gpt-5-mini",
        "Cost: ~$0.10",
        "Time: ~5-8 minutes",
        "Compliance: PASS",
        "Docs enrichment: 5 chunks from official sources",
    ]
    y = 260
    for s in stats:
        draw.text((WIDTH // 2 - 150, y), s, fill=WHITE, font=small)
        y += 30

    draw.text((WIDTH // 2 - 100, 450), "Copy -> Paste to Medium", fill=HEDERA_PURPLE, font=med)
    return img


def create_gif(output_path):
    frames = []

    # Title (show 2 sec = 2 frames at 1000ms)
    frames.append(make_frame_title())
    frames.append(make_frame_title())

    # Fetch livestreams
    frames.append(make_frame_fetch())
    frames.append(make_frame_fetch())

    # Settings
    frames.append(make_frame_settings())
    frames.append(make_frame_settings())

    # Pipeline steps (each ~1 sec)
    for step in range(12):
        frames.append(make_frame_pipeline(step))

    # Output (show 3 sec)
    for _ in range(3):
        frames.append(make_frame_output())

    # End (show 2 sec)
    frames.append(make_frame_end())
    frames.append(make_frame_end())

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=1000,  # 1 second per frame
        loop=0,
    )
    print(f"GIF created: {output_path} ({len(frames)} frames)")


if __name__ == "__main__":
    create_gif("docs/HederaContentCreatorHelper_Demo.gif")
