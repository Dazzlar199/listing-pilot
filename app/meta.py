"""Thin wrappers around the Meta Model API (OpenAI-compatible, https://api.meta.ai/v1).

Models used:
  muse-spark-1.3   vision understanding, listing copy, semantic image review
  sam-3.1          product segmentation (mask)
  muse-image-1.0   lifestyle / in-context images built from the cut-out

With no MODEL_API_KEY (or LP_MOCK=1) every call returns a canned answer so the
UI and the checkers can be developed without spending credits.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
from contextlib import aclosing
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

BASE_URL = "https://api.meta.ai/v1"
TEXT_MODEL = os.environ.get("LP_TEXT_MODEL", "muse-spark-1.3")
IMAGE_MODEL = "muse-image-1.0"
SAM_MODEL = "sam-3.1"


def mock_mode() -> bool:
    return os.environ.get("LP_MOCK") == "1" or not os.environ.get("MODEL_API_KEY")


def _client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ["MODEL_API_KEY"], base_url=BASE_URL, max_retries=3, timeout=180)


def _aclient():
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=os.environ["MODEL_API_KEY"], base_url=BASE_URL, max_retries=3, timeout=180)


def data_url(img: Image.Image, fmt: str = "JPEG", max_side: int = 1600) -> str:
    im = img.convert("RGB")
    if max(im.size) > max_side:
        im = im.copy()
        im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, fmt, quality=90)
    mime = "image/jpeg" if fmt == "JPEG" else f"image/{fmt.lower()}"
    return f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode()}"


def _json_call(system: str, user_content: list[dict] | str, schema: dict, name: str,
               effort: str = "low") -> dict:
    """Chat Completions with a JSON schema; returns the parsed object."""
    r = _client().chat.completions.create(
        model=TEXT_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user_content}],
        response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema}},
        reasoning_effort=effort,
    )
    return json.loads(r.choices[0].message.content)


# --------------------------------------------------------------------------- 1. understand the photo

FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "sam_noun": {"type": "string", "description": "1-3 word concrete noun phrase covering the WHOLE item as sold, "
                                                    "including its container or lid (e.g. 'candle jar' not 'candle', "
                                                    "'water bottle', 'mug')"},
        "sam_noun_alt": {"type": "string", "description": "a different noun phrase for the same whole item, used if the "
                                                        "first one segments only part of it (e.g. 'glass jar')"},
        "product_name": {"type": "string"},
        "category": {"type": "string"},
        "color": {"type": "string"},
        "material": {"type": "string"},
        "visible_features": {"type": "array", "items": {"type": "string"}},
        "visible_text_or_logos": {"type": "array", "items": {"type": "string"}},
        "props_in_photo": {"type": "array", "items": {"type": "string"}},
        "uncertain": {"type": "array", "items": {"type": "string"},
                       "description": "facts a seller must confirm (size, capacity, material) because the photo cannot prove them"},
        "seller_notes_en": {"type": "string", "description": "faithful English translation of the seller notes, "
                                                           "keeping every claim word for word; empty if none"},
        "seller_specs": {"type": "array", "items": {"type": "string"},
                         "description": "specs stated by the seller (size, capacity, material, scent, care), in English"},
        "scene_ideas": {"type": "array", "items": {"type": "string"},
                        "description": "2 realistic in-use scenes for a US shopper, each clearly different from the "
                                       "original photo's setting and from each other (e.g. office desk, gift moment)"},
    },
    "required": ["sam_noun", "sam_noun_alt", "product_name", "category", "color", "material", "visible_features",
                 "visible_text_or_logos", "props_in_photo", "uncertain", "seller_notes_en", "seller_specs", "scene_ideas"],
}


def understand(photo: Image.Image, seller_notes: str = "") -> dict:
    if mock_mode():
        return {
            "sam_noun": "mug", "sam_noun_alt": "cup", "product_name": "Speckled ceramic coffee mug", "category": "Home & Kitchen > Mugs",
            "color": "cream with brown speckles", "material": "ceramic (stoneware look)",
            "visible_features": ["wide C-shaped handle", "matte speckled glaze", "straight cylinder body"],
            "visible_text_or_logos": [], "props_in_photo": ["wooden table", "coffee beans"],
            "uncertain": ["capacity in oz", "dishwasher and microwave safe"],
            "seller_notes_en": "", "seller_specs": [],
            "scene_ideas": ["morning coffee on a sunlit kitchen counter", "desk with laptop and notebook"],
        }
    content = [
        {"type": "text", "text": "Describe only what this product photo shows. Seller notes (trust these over guesses): "
                                 + (seller_notes or "none")},
        {"type": "image_url", "image_url": {"url": data_url(photo)}},
    ]
    return _json_call(
        "You are an Amazon catalog specialist. Seller notes are the seller's confirmed facts: copy their specs into "
        "seller_specs and do not list them as uncertain. Never invent specs that neither the photo nor the seller gives; "
        "put those in 'uncertain'.",
        content, FACTS_SCHEMA, "ProductFacts")


# --------------------------------------------------------------------------- 2. segment

async def _sam(photo: Image.Image, noun: str):
    from meta_sam_parser import image_segmentation_format, parse_responses_stream

    async def events(stream):
        done: set = set()
        async for ev in stream:
            d = ev.model_dump() if hasattr(ev, "model_dump") else dict(ev)
            lane = (d.get("item_id"), d.get("output_index"), d.get("content_index"))
            if d.get("type") == "response.output_text.done":
                if lane not in done:
                    done.add(lane)
                    yield d
                continue
            yield d
            part = d.get("part")
            if (d.get("type") == "response.content_part.done" and lane not in done and isinstance(part, dict)
                    and part.get("type") == "output_text" and isinstance(part.get("text"), str)):
                done.add(lane)
                yield {"type": "response.output_text.done", "item_id": d.get("item_id"),
                       "output_index": d.get("output_index"), "content_index": d.get("content_index"),
                       "text": part["text"]}

    async with _aclient() as api:
        stream = await api.responses.create(
            model=SAM_MODEL, stream=True, metadata={"include_confidence": "true"},
            input=[{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": noun},
                {"type": "input_image", "image_url": data_url(photo, "PNG", max_side=2048)}]}])
        async with stream, aclosing(events(stream)) as evs:
            return await parse_responses_stream(evs, image_segmentation_format()).final_result()


def _mask_to_frame(rec, size: tuple[int, int]) -> np.ndarray:
    from meta_sam_parser import decode_mask_to_raster
    m = rec.mask
    raster = np.frombuffer(decode_mask_to_raster(m), dtype=np.uint8).reshape(m.height, m.width)
    W, H = size
    b = rec.bounds
    if b is not None and (b.right - b.left) > 0 and (b.bottom - b.top) > 0 and \
            not (b.left == 0 and b.top == 0 and b.right >= W - 1 and b.bottom >= H - 1):
        region = (int(b.left), int(b.top), int(b.right), int(b.bottom))
    else:
        region = (0, 0, W, H)
    rw, rh = max(1, region[2] - region[0]), max(1, region[3] - region[1])
    small = Image.fromarray(raster * 255, "L").resize((rw, rh), Image.NEAREST)
    full = Image.new("L", (W, H), 0)
    full.paste(small, region[:2])
    return (np.asarray(full) > 127).astype(np.uint8)


def segment(photo: Image.Image, noun: str) -> tuple[np.ndarray, dict]:
    """Return (mask HxW 0/1 for the largest match, info)."""
    photo = photo.convert("RGB")
    if mock_mode():
        return _mock_mask(photo), {"matches": 1, "confidence": None, "mock": True}
    sent = photo.copy()
    sent.thumbnail((2048, 2048))
    result = asyncio.run(_sam(sent, noun))
    masks = [r for r in result.records if getattr(r, "kind", "") == "mask"]
    if not masks:
        return np.zeros((photo.height, photo.width), np.uint8), {"matches": 0}
    best, best_area, conf = None, -1, None
    for r in masks:
        m = _mask_to_frame(r, sent.size)
        if m.sum() > best_area:
            best, best_area, conf = m, int(m.sum()), getattr(r, "confidence", None)
    full = Image.fromarray(best * 255, "L").resize(photo.size, Image.NEAREST)
    return (np.asarray(full) > 127).astype(np.uint8), {"matches": len(masks), "confidence": conf}


def _mock_mask(photo: Image.Image) -> np.ndarray:
    """Non-background pixels of the sample photo (works for the bundled samples)."""
    a = np.asarray(photo.convert("RGB"), dtype=np.int16)
    corner = np.median(np.concatenate([a[:10, :10].reshape(-1, 3), a[-10:, -10:].reshape(-1, 3)]), axis=0)
    return (np.abs(a - corner).sum(axis=2) > 60).astype(np.uint8)


# --------------------------------------------------------------------------- 3. lifestyle images

def lifestyle(cutout: Image.Image, scene: str, facts: dict) -> Image.Image:
    prompt = (f"Photorealistic Amazon lifestyle photo: the exact product from the reference image ({facts['product_name']}) "
              f"in this scene: {scene}. Keep the product's shape, color, glaze and proportions identical. "
              "No text, no logos, no watermark, no people's faces. Natural light, square framing.")
    if mock_mode():
        return _mock_scene(cutout, scene)
    buf = io.BytesIO()
    cutout.convert("RGB").save(buf, "PNG")
    buf.seek(0)
    buf.name = "product.png"
    r = _client().images.edit(model=IMAGE_MODEL, prompt=prompt, image=buf, n=1, size="1024x1024",
                              extra_body={"reasoning_strength": "low",
                                          "tool_enablement": {"enable_image_search": False, "enable_web_search": False,
                                                              "enable_shell": False}})
    return Image.open(io.BytesIO(base64.b64decode(r.data[0].b64_json))).convert("RGB")


def _mock_scene(cutout: Image.Image, scene: str) -> Image.Image:
    bg = Image.new("RGB", (1024, 1024), (214, 196, 170))
    d = ImageDraw.Draw(bg)
    d.rectangle([0, 640, 1024, 1024], fill=(150, 112, 80))
    item = cutout.copy()
    item.thumbnail((560, 560))
    bg.paste(item, ((1024 - item.width) // 2, 640 - item.height + 80))
    d.text((24, 24), f"[mock] {scene}", fill=(60, 50, 40))
    return bg


# --------------------------------------------------------------------------- 4. listing copy

LISTING_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 5},
        "description": {"type": "string"},
        "search_terms": {"type": "string", "description": "space separated, lowercase, no commas"},
    },
    "required": ["title", "bullets", "description", "search_terms"],
}


def write_listing(facts: dict, brand: str, rules_brief: str, feedback: list[str] | None = None,
                  previous: dict | None = None, seller_notes: str = "") -> dict:
    if mock_mode():
        return _mock_listing(feedback)
    task = {"facts": facts, "brand": brand, "seller_notes": seller_notes, "rules": rules_brief}
    if feedback:
        task["previous_attempt"] = previous
        task["fix_only_these_violations"] = feedback
    return _json_call(
        "You write Amazon.com (US) listings for small sellers that convert shoppers. Follow every rule exactly. "
        "Title: brand, then what it is in shopper words (e.g. 'Ceramic Coffee Mug'), then the key look or feature. "
        "Bullets: each starts with a short benefit label in Title Case followed by ' - ', then a concrete sentence on "
        "why it matters to the buyer (look, feel, use, care, gifting). Seller notes may be in any language (often "
        "Korean). facts.seller_specs are confirmed: always use them (size, material, scent, burn time, care) in the title "
        "and bullets. Keep the seller's selling points only where Amazon rules allow; drop restricted claims silently. "
        "Write natural US English. Describe the product as sold, never as "
        "'pictured' and never the props or contents in the photo. Use only facts given; for 'uncertain' facts write "
        "nothing rather than guess. Description: 2 short paragraphs a shopper would enjoy reading. "
        "When fixing, change only what the violations require and keep everything else.",
        json.dumps(task, ensure_ascii=False), LISTING_SCHEMA, "Listing", effort="medium")


def _mock_listing(feedback):
    if feedback:
        return {
            "title": "Hearth & Clay Ceramic Coffee Mug, Speckled Cream Glaze, Wide C Handle",
            "bullets": [
                "Speckled matte glaze in warm cream with brown flecks for a handmade stoneware look",
                "Wide C-shaped handle leaves room for two fingers for a steady grip",
                "Straight cylinder body is easy to hold and simple to rinse clean",
                "Neutral color fits farmhouse, minimalist and rustic kitchens",
                "A thoughtful gift for coffee and tea drinkers",
            ],
            "description": "A speckled ceramic mug for slow mornings. The matte cream glaze with brown flecks gives it a handmade stoneware look, and the wide handle sits comfortably in the hand.",
            "search_terms": "stoneware cup farmhouse rustic tea latte cappuccino matte speckle handmade look",
        }
    return {
        "title": "Hearth & Clay Ceramic Coffee Mug!! BEST SELLER - Speckled Mug, Mug, Mug for Coffee | FREE SHIPPING",
        "bullets": [
            "Speckled matte glaze in warm cream with brown flecks for a handmade stoneware look",
            "Wide C-shaped handle leaves room for two fingers for a steady grip",
            "100% guaranteed to make your mornings better ☕",
            "Neutral color fits farmhouse, minimalist and rustic kitchens",
            "A thoughtful gift for coffee and tea drinkers",
        ],
        "description": "A speckled ceramic mug for slow mornings. Visit www.hearthclay.example for more.",
        "search_terms": "Hearth & Clay, coffee mug, mug, stoneware cup, best mug, B0EXAMPLE1",
    }


# --------------------------------------------------------------------------- 5. semantic image review

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "has_text_or_logo": {"type": "boolean"},
        "has_props_or_extra_items": {"type": "boolean"},
        "has_border_or_graphics": {"type": "boolean"},
        "product_matches_reference": {"type": "boolean"},
        "cutout_artifacts": {"type": "boolean",
                             "description": "true if the product looks cut out badly: see-through holes where the product "
                                            "should be solid or filled, missing parts, leftover background, jagged edges"},
        "would_pass_as_studio_photo": {"type": "boolean"},
        "notes": {"type": "string", "description": "one sentence naming each problem found"},
    },
    "required": ["has_text_or_logo", "has_props_or_extra_items", "has_border_or_graphics",
                 "product_matches_reference", "cutout_artifacts", "would_pass_as_studio_photo", "notes"],
}


def review_image(img: Image.Image, reference: Image.Image, role: str) -> dict:
    if mock_mode():
        return {"has_text_or_logo": False, "has_props_or_extra_items": False, "has_border_or_graphics": False,
                "product_matches_reference": True, "cutout_artifacts": False, "would_pass_as_studio_photo": True,
                "notes": "mock review"}
    content = [
        {"type": "text", "text": f"Image 1 is a candidate {role} image for an Amazon listing. Image 2 is the seller's "
                                 "original photo. Answer strictly about what is visible in image 1. Look closely at the inside of "
                                 "openings (cup interiors, handles, rims): a flat white patch where the product's inside or "
                                 "contents should be is a cut-out artifact."},
        {"type": "image_url", "image_url": {"url": data_url(img)}},
        {"type": "image_url", "image_url": {"url": data_url(reference)}},
    ]
    return _json_call("You are a strict Amazon image compliance reviewer.", content, REVIEW_SCHEMA, "ImageReview",
                      effort="medium")


# --------------------------------------------------------------------------- 6. studio retouch (repair path)

def studio_retouch(photo: Image.Image, facts: dict, problems: str) -> Image.Image:
    """Ask Muse Image for a clean studio packshot of the same product; SAM + compositor then make it exact."""
    prompt = (f"Professional e-commerce studio packshot of the exact {facts['product_name']} from the reference photo. "
              f"Empty, clean product only, as it is sold, on a plain light grey seamless background, soft even light, "
              f"three-quarter front view, whole product visible. Keep shape, color, glaze, pattern and proportions identical. "
              f"Remove everything else ({', '.join(facts.get('props_in_photo', [])[:6]) or 'props'}). "
              f"Fix these problems from the previous attempt: {problems}. No text, no logo, no shadow props.")
    if mock_mode():
        return photo
    buf = io.BytesIO()
    photo.convert("RGB").save(buf, "JPEG", quality=92)
    buf.seek(0)
    buf.name = "photo.jpg"
    r = _client().images.edit(model=IMAGE_MODEL, prompt=prompt, image=buf, n=1, size="1024x1024",
                              extra_body={"reasoning_strength": "high",
                                          "tool_enablement": {"enable_image_search": False, "enable_web_search": False,
                                                              "enable_shell": False}})
    return Image.open(io.BytesIO(base64.b64decode(r.data[0].b64_json))).convert("RGB")
