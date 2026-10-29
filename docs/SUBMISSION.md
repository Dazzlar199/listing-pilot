# Submission: Meta Global AI Developer Hackathon

**Project name:** Listing Pilot

**Tagline:** One product photo in. A compliance-checked Amazon listing out.

**Track:** Indie developer
**Theme:** Build for Your World

**Repository:** https://github.com/Dazzlar199/listing-pilot
**Demo video:** <VIDEO LINK>

## Description

Small Amazon sellers start with a phone photo on a cluttered table and a few notes, often not in English. Amazon then expects a pure white main image with the product filling about 85% of the frame, a title of 75 characters or fewer, and copy without restricted claims such as "eco-friendly", "non-toxic" or "full refund". One mistake and the listing can be suppressed. A plain prompt does not reliably follow these rules, and image generators drift away from the real product.

Listing Pilot is an agent that turns that one photo into a compliance-checked listing package. Muse Spark reads the photo and the seller's notes in any language, separates the product from the props, and flags restricted claims. SAM 3.1 cuts the product out, and the result is placed on pure white. Muse Spark then reviews the composite against the original. If it fails, Muse Image re-shoots the product as a clean studio packshot and the loop runs again. Muse Spark writes the title, bullets, description and search terms, and a rule engine checks them against Amazon's published rules. Only the failed rules go back to the model. Muse Image stages lifestyle shots, and Muse Spark checks that the product still matches. The seller downloads the images, JSON and CSV in one zip, with a compliance report.

The models decide what the product is and where it is. Plain code decides whether it passes, so a model cannot talk its way past a rule.

## How Meta models are used

- **Muse Spark (`muse-spark-1.3`)**: vision understanding of the seller photo and notes (JSON schema output), strict visual review of every generated image against the original, listing copy, and targeted fixes when the rule engine fails it.
- **SAM 3.1 (`sam-3.1`)**: text-prompted product segmentation ("candle jar") through the Responses API stream, decoded with `meta-sam-parser`.
- **Muse Image (`muse-image-1.0`)**: the repair path (a studio re-shoot when the cut-out fails review) and lifestyle images built from the approved cut-out.

All three are called through the Meta Model API (OpenAI-compatible endpoint).

## Built during the hackathon

New repository, first commit Oct 28, 2026. MIT licensed. Sample product photos were generated with Muse Image, so the demo uses no third-party photos.
