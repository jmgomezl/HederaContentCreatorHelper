# Bypass YouTube IP rate limits with cookies

If you see errors like:

> YouTube is blocking requests from your IP

...YouTube has temporarily rate-limited your IP. The fix is to authenticate
as a logged-in user by exporting your browser cookies.

## Step 1: Install a cookies export extension

**Chrome/Brave/Edge:**
- Install [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- Read the extension reviews first — use one that exports LOCALLY only (no cloud upload)

**Firefox:**
- Install [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

**Safari:**
- Use a different browser for the cookies export (Safari doesn't have good extensions for this)

## Step 2: Export cookies

1. Open https://www.youtube.com in your browser
2. Make sure you're **logged in** (your avatar should appear top-right)
3. Click the extension icon
4. Click **Export** or **Download** (it will save `cookies.txt`)

## Step 3: Save the file

Move `cookies.txt` into the project root:

```bash
mv ~/Downloads/cookies.txt /Users/juan/JuanMa/Training/HederaContentCreatorHelper/cookies.txt
```

This file is **gitignored** automatically — it contains session tokens that
are equivalent to your YouTube login, so NEVER commit it or share it.

## Step 4: Point the app at the file

Add to your `.env`:

```bash
YOUTUBE_COOKIES_PATH=/Users/juan/JuanMa/Training/HederaContentCreatorHelper/cookies.txt
```

## Step 5: For the Mac mini

SSH in and copy the cookies file over:

```bash
scp cookies.txt juanma_bot@bot.local:~/HederaContentCreatorHelper/cookies.txt
ssh juanma_bot@bot.local "echo 'YOUTUBE_COOKIES_PATH=/Users/juanma_bot/HederaContentCreatorHelper/cookies.txt' >> ~/HederaContentCreatorHelper/.env"
```

## Notes

- Cookies usually last 6-12 months before YouTube rotates them
- If you see the IP block error again, re-export and re-copy the cookies file
- The fetch_transcript() function automatically retries with exponential backoff
  (4s, 16s, 64s) for transient rate-limit errors even without cookies
