"""Amazon.com (US) listing rules used by the checker, with where each one comes from.

severity "fail"  = stated in a public Amazon-owned source (Seller Forums post by an Amazon
                   account, globalselling.amazon.com, or an Amazon style guide)
severity "warn"  = commonly enforced but not quotable from a public official page; shown as a
                   warning so the seller decides
Checked 2026-10-28. Help pages on sellercentral.amazon.com are login-gated, so every rule
links to the public source we could read.
"""

SRC_IMG = "https://sellercentral.amazon.com/seller-forums/discussions/t/0149bdb3-2056-42ce-b0bb-9eef94e3d2b8"
SRC_IMG2 = "https://sellercentral.amazon.com/seller-forums/discussions/t/13af96ea-6b07-4bf9-8dbe-a13292c2e3b1"
SRC_TITLE_75 = "https://sellercentral.amazon.com/seller-forums/discussions/t/145b6d0f-999c-4555-896c-c694bda2e470"
SRC_TITLE_2025 = "https://sellercentral.amazon.com/seller-forums/discussions/t/b2b15728-0d43-453e-974f-59eb63f73059"
SRC_TITLE_GS = "https://globalselling.amazon.com/news/news-notices-250120"
SRC_BULLETS = "https://sellercentral.amazon.com/seller-forums/discussions/t/65f8e647-977d-49ac-9036-2049b96720b2"
SRC_BULLETS_GS = "https://globalselling.amazon.com/zhishi/article-250307-3"
SRC_STYLE = "https://images-na.ssl-images-amazon.com/images/G/01/rainier/help/Home_Garden_and_Pets-Style_Guide.pdf"
SRC_KEYWORDS = "https://sellercentral.amazon.com/seller-forums/discussions/t/8e1ad5d2-5d5f-4086-bda3-735505e23bb1"
SRC_PESTICIDE = "https://sellercentral.amazon.com/seller-forums/discussions/t/d0fc2e9e-3b19-462c-806d-317f9cd2934a"

IMAGE = {
    "min_longest_side_px": 1000,     # zoom
    "max_longest_side_px": 10000,
    "white_frame_share": 0.995,      # border pixels that are exactly 255,255,255
    "min_fill_ratio": 0.85,
}

TITLE_MAX = 75                       # all non-media categories from 2026-07-27
BULLET_MIN, BULLET_MAX = 10, 255
DESCRIPTION_MAX = 2000
SEARCH_TERMS_MAX_BYTES = 249

MINOR_WORDS = {"a", "an", "the", "and", "or", "for", "nor", "but", "so", "yet", "in", "on", "over",
               "with", "at", "by", "to", "of", "from"}

TITLE_BAD_CHARS = "!$?_{}^¬¦"
BULLET_BAD_CHARS = "™®©€…~†‡¢£¥±"
PROMO_PHRASES = ["free shipping", "best seller", "bestseller", "hot item", "100% quality guaranteed",
                 "great value", "hot this year", "on sale", "best price", "cheapest", "limited time"]
GUARANTEE_PHRASES = ["full refund", "money back", "if not satisfied", "unconditional guarantee",
                     "lifetime guarantee", "100% guaranteed", "guaranteed"]
BULLET_BANNED = ["eco-friendly", "environmentally friendly", "ecologically friendly", "anti-microbial",
                 "antimicrobial", "anti-bacterial", "antibacterial", "made from bamboo", "contains bamboo",
                 "made from soy", "contains soy"]
PESTICIDE = ["antifungal", "anti-fungal", "antiviral", "kills germs", "kills bacteria", "kills viruses",
             "99.9%", "sanitize", "sanitizer", "disinfect", "mold resistant", "mildew resistant",
             "prevents mold", "repels insects", "insect repellent", "epa approved", "chemical-free", "chemical free"]
UNVERIFIED_CLAIMS = ["non-toxic", "biodegradable", "compostable", "fda approved", "cures", "treats", "prevents disease"]
SEARCH_BANNED = ["best", "cheapest", "on sale", "available now", "new", "amazing", "top rated"]
PLACEHOLDERS = {"na", "n/a", "not applicable", "tbd"}

# What the copywriter model is told (kept short; the checker is the source of truth).
BRIEF = f"""Amazon.com US listing rules:
- Title: at most {TITLE_MAX} characters including spaces. Format: Brand + product type + key attribute(s).
  No {' '.join(TITLE_BAD_CHARS)} characters. No word more than twice. No ALL CAPS words.
  Capitalize each word except short articles, conjunctions and prepositions. No promotional or subjective words.
- Exactly 5 bullets, each {BULLET_MIN}-{BULLET_MAX} characters, starting with a capital letter, all different.
  No emojis, no {BULLET_BAD_CHARS} symbols, no guarantees or refund wording, no URLs or contact info,
  no eco-friendly / antimicrobial / antibacterial or other pesticide or health claims.
- Description: at most {DESCRIPTION_MAX} characters, plain sentences, no URLs, emails, phone numbers, no promotion.
- Search terms: at most {SEARCH_TERMS_MAX_BYTES} bytes, lowercase, space separated, no brand names, no ASINs,
  no words already in the title, no repeated words, no subjective or time-sensitive words."""
