# Hedera Tags and Gist Embed Test

*Verifying that tags pills render and code blocks become Gist embeds for Medium import.*

## Why this matters

Medium has two persistent pain points when importing technical content:

1. Code blocks get flattened to single lines via the URL importer
2. Tags must be added manually after each import

This post tests both fixes simultaneously.

## How the fix works

When the blog has fenced code blocks, the publisher creates a GitHub Gist for each block and saves a parallel `-medium.md` file with Gist URLs in place of the original code.

When you import the `-medium.md` file via Medium's importer, each Gist URL becomes a properly formatted, syntax-highlighted code embed.



https://gist.github.com/jmgomezl/afe1a7e2d3e80940d59b78d40632785d



For JavaScript users, the SDK looks similar:



https://gist.github.com/jmgomezl/5583e41a066358cd3c12896242ad383d



## Key takeaways

- Code blocks now embed properly when imported to Medium via Gists
- Tags appear as pills at the bottom of the article
- The cover image is rendered above the title
- All steps are automated end-to-end in the weekly publisher

## Resources

- [Hedera SDK docs](https://docs.hedera.com/hedera/sdks)
- [Medium import tool](https://medium.com/p/import)
