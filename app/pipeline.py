"""The listing agent: photo in, checked Amazon listing package out.

Each step emits events so the UI can show the agent working. Every output is checked;
failures are fed back to the model that produced them, and only failing parts are redone.
"""
from __future__ import annotations

import csv
import io
import json
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from . import checks, imaging, meta, rules

OUT = Path(__file__).resolve().parents[1] / "out"
MAX_IMAGE_TRIES = 3
MAX_TEXT_TRIES = 3


@dataclass
class Run:
    id: str
    dir: Path
    events: list[dict] = field(default_factory=list)
    result: dict = field(default_factory=dict)
    done: bool = False
    error: str | None = None
    listeners: list[Callable[[dict], None]] = field(default_factory=list)

    def emit(self, step: str, status: str, msg: str, **data):
        ev = {"t": round(time.time(), 2), "step": step, "status": status, "msg": msg, **data}
        self.events.append(ev)
        for fn in list(self.listeners):
            fn(ev)

    def url(self, name: str) -> str:
        return f"/runs/{self.id}/{name}"

    def save(self, img: Image.Image, name: str, quality: int = 92) -> str:
        img.convert("RGB").save(self.dir / name, quality=quality)
        return self.url(name)


def new_run() -> Run:
    rid = time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    d = OUT / rid
    d.mkdir(parents=True, exist_ok=True)
    return Run(rid, d)


def _image_problems(pix: imaging.ImageReport, review: dict) -> list[str]:
    probs = [c.detail for c in pix.failed()]
    if review.get("cutout_artifacts"):
        probs.append("cut-out artifact: " + review.get("notes", ""))
    if review.get("has_props_or_extra_items"):
        probs.append("props or extra items visible")
    if review.get("has_text_or_logo"):
        probs.append("text or logo visible")
    if review.get("has_border_or_graphics"):
        probs.append("border or graphics")
    if not review.get("product_matches_reference", True):
        probs.append("product no longer matches the seller's photo")
    if not review.get("would_pass_as_studio_photo", True) and not probs:
        probs.append("does not look like a clean studio photo: " + review.get("notes", ""))
    return probs


def make_main_image(run: Run, photo: Image.Image, facts: dict) -> dict:
    source, source_name = photo, "seller photo"
    noun = facts["sam_noun"]
    history = []
    for attempt in range(1, MAX_IMAGE_TRIES + 1):
        run.emit("main_image", "work", f"Attempt {attempt}: SAM 3.1 segments the '{noun}' in the {source_name}")
        mask, info = meta.segment(source, noun)
        if info.get("matches", 0) == 0:
            run.emit("main_image", "warn", "SAM 3.1 found no match; asking Muse Image for a clean studio shot")
            problems = ["segmentation found no product"]
        else:
            mask, holes = imaging.fill_enclosed_holes(source, mask)
            if holes["filled"]:
                run.emit("main_image", "work", f"Filled {holes['filled']} enclosed part(s) SAM left out; "
                                               f"kept {holes['kept_open']} real opening(s)")
            mask_url = run.save(Image.fromarray(mask * 255), f"mask_{attempt}.png")
            main = imaging.compose_on_white(source, mask)
            url = run.save(main, f"main_{attempt}.jpg", quality=95)
            pix = imaging.check_main_image(main, rules.IMAGE)
            run.emit("main_image", "work", "Spark reviews the composite against the original photo", image=url, mask=mask_url,
                     confidence=info.get("confidence"))
            review = meta.review_image(main, photo, "main")
            problems = _image_problems(pix, review)
            history.append({"attempt": attempt, "image": url, "source": source_name,
                            "pixel_checks": [c.__dict__ for c in pix.checks], "review": review, "problems": problems})
            if not problems:
                run.emit("main_image", "pass", f"Main image passes all checks on attempt {attempt}", image=url,
                         checks=[c.__dict__ for c in pix.checks], review=review)
                return {"image": url, "file": f"main_{attempt}.jpg", "attempts": history}
            run.emit("main_image", "fail", "Found: " + "; ".join(problems), image=url, problems=problems)
        if attempt == MAX_IMAGE_TRIES:
            break
        partial = any(w in " ".join(problems).lower() for w in ("missing", "only part", "cropped", "partial"))
        if partial and facts.get("sam_noun_alt") and noun != facts["sam_noun_alt"]:
            noun = facts["sam_noun_alt"]
            run.emit("main_image", "work", f"Only part of the product was cut out; switching the SAM prompt to '{noun}'")
        run.emit("main_image", "work", "Muse Image re-shoots the product as a clean studio packshot")
        source = meta.studio_retouch(photo, facts, "; ".join(problems))
        source_name = "Muse Image studio shot"
        run.emit("main_image", "work", "Studio shot ready", image=run.save(source, f"studio_{attempt}.jpg"))
    run.emit("main_image", "fail", "Could not produce a compliant main image; seller must review")
    last = history[-1] if history else {}
    return {"image": last.get("image"), "file": None, "attempts": history, "needs_review": True}


def make_listing(run: Run, facts: dict, brand: str, notes: str = "") -> dict:
    listing, feedback, history = None, None, []
    for attempt in range(1, MAX_TEXT_TRIES + 1):
        verb = "writes" if attempt == 1 else "fixes only the flagged parts of"
        run.emit("listing", "work", f"Attempt {attempt}: Spark {verb} the title, 5 bullets, description and search terms")
        listing = meta.write_listing(facts, brand, rules.BRIEF, feedback, listing, notes)
        found = checks.check_listing(listing, brand)
        fails = [v for v in found if v.severity == "fail"]
        warns = [v for v in found if v.severity == "warn"]
        history.append({"attempt": attempt, "listing": listing, "violations": [v.as_dict() for v in found]})
        run.emit("listing", "pass" if not fails else "fail",
                 f"{len(fails)} rule violation(s), {len(warns)} warning(s)", listing=listing,
                 violations=[v.as_dict() for v in found])
        if not fails:
            return {"listing": listing, "attempts": history, "warnings": [v.as_dict() for v in warns]}
        feedback = [f"{v.field}: {v.message}" for v in fails]
    return {"listing": listing, "attempts": history, "needs_review": True,
            "warnings": [v.as_dict() for v in found]}


def make_lifestyle(run: Run, main_file: str | None, photo: Image.Image, facts: dict) -> list[dict]:
    if not main_file:
        return []
    cutout = Image.open(run.dir / main_file)
    shots = []
    for i, scene in enumerate(facts.get("scene_ideas", [])[:2], 1):
        run.emit("lifestyle", "work", f"Muse Image stages the product: {scene}")
        img = meta.lifestyle(cutout, scene, facts)
        url = run.save(img, f"lifestyle_{i}.jpg")
        review = meta.review_image(img, photo, "secondary lifestyle")
        ok = review.get("product_matches_reference", True) and not review.get("has_text_or_logo")
        if not ok:
            run.emit("lifestyle", "fail", "Product drifted from the original; regenerating once", image=url)
            img = meta.lifestyle(cutout, scene + ". The product must look exactly like the reference.", facts)
            url = run.save(img, f"lifestyle_{i}.jpg")
            review = meta.review_image(img, photo, "secondary lifestyle")
            ok = review.get("product_matches_reference", True) and not review.get("has_text_or_logo")
        run.emit("lifestyle", "pass" if ok else "warn",
                 "Product matches the seller's photo" if ok else "Check this image by hand", image=url)
        shots.append({"image": url, "file": f"lifestyle_{i}.jpg", "scene": scene, "review": review, "ok": ok})
    return shots


def package(run: Run, result: dict) -> str:
    listing = result["listing"]["listing"]
    result["package"] = run.url("listing_package.zip")  # in listing.json too, so the UI's download link works
    with open(run.dir / "listing.json", "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["item_name", "bullet_point1", "bullet_point2", "bullet_point3", "bullet_point4", "bullet_point5",
                "product_description", "generic_keywords", "main_image", "other_image1", "other_image2"])
    life = [s["file"] for s in result.get("lifestyle", [])]
    w.writerow([listing["title"], *(listing["bullets"] + [""] * 5)[:5], listing["description"],
                listing["search_terms"], result["main"].get("file") or "", *(life + ["", ""])[:2]])
    (run.dir / "listing.csv").write_text(buf.getvalue())
    zpath = run.dir / "listing_package.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ["listing.json", "listing.csv", result["main"].get("file"), *life]:
            if name:
                z.write(run.dir / name, name)
    return run.url("listing_package.zip")


def run_pipeline(run: Run, photo: Image.Image, brand: str, notes: str = "") -> dict:
    try:
        photo = imaging.load_rgb(photo)
        run.save(photo, "input.jpg")
        run.emit("understand", "work", "Spark looks at the photo: what is the product, what is just a prop, what can't be known")
        facts = meta.understand(photo, notes)
        run.emit("understand", "pass", f"Product: {facts['product_name']}", facts=facts)
        flagged = checks.check_seller_notes(facts.get("seller_notes_en", ""))
        if flagged:
            run.emit("understand", "warn", f"Your notes contain {len(flagged)} phrase(s) Amazon restricts; "
                                           "the agent will leave them out", violations=[v.as_dict() for v in flagged])
        facts["notes_flagged"] = [v.as_dict() for v in flagged]

        main = make_main_image(run, photo, facts)
        listing = make_listing(run, facts, brand, notes)
        life = make_lifestyle(run, main.get("file"), photo, facts)
        result = {"brand": brand, "facts": facts, "main": main, "listing": listing, "lifestyle": life}
        result["package"] = package(run, result)
        run.result = result
        run.emit("package", "pass", "Listing package ready", package=result["package"])
        return result
    except Exception as e:  # surface, don't hide
        run.error = f"{type(e).__name__}: {e}"
        run.emit("error", "fail", run.error)
        raise
    finally:
        (run.dir / "events.json").write_text(json.dumps(run.events, ensure_ascii=False))
        run.done = True
