"""Record the demo video against the live Meta Model API (one real run on the candle sample).

Steps:
  1. app running with a real MODEL_API_KEY:  .venv/bin/uvicorn app.server:app --port 8822
  2. narration:  cd ../cyclopedia_upgrade && PYTHONPATH=. .venv/bin/python ../listing-pilot/scripts/demo_tts.py
  3. this script (needs playwright):  python scripts/record_demo.py
Waits where the agent is working and nobody is talking are recorded with a "fast-forward" badge and sped up 4x
in the final cut, so the video stays under three minutes while every frame comes from the real run.
If Playwright's bundled ffmpeg is too old for record_video, set PLAYWRIGHT_BROWSERS_PATH to a folder whose
ffmpeg-<rev>/ffmpeg-mac wraps a current ffmpeg (and symlinks the chromium dirs).
Output: docs/demo/listing_pilot_demo.mp4, README screenshots in docs/screenshots/ (work files in docs/demo/work, git-ignored)."""
import glob, json, os, re, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
from demo_lines import LINES
W = ROOT / "docs" / "demo" / "work"; OUTMP4 = ROOT / "docs" / "demo" / "listing_pilot_demo.mp4"
SHOTS = ROOT / "docs" / "screenshots"; SHOTS.mkdir(parents=True, exist_ok=True)
DUR = json.loads((W / "durations.json").read_text())
B = os.environ.get("LP_URL", "http://localhost:8822")
FAST = 4.0
exe = os.environ.get("CHROMIUM_PATH") or (sorted(glob.glob(os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"))) or [None])[-1]

INIT = r"""
(() => {
  const css = `#__sub{position:fixed;left:50%;bottom:30px;transform:translateX(-50%);max-width:1600px;width:max-content;padding:12px 26px;background:rgba(10,12,14,.84);color:#fff;font:600 31px/1.35 -apple-system,Helvetica,Arial,sans-serif;text-align:center;border-radius:12px;z-index:2147483647;display:none;pointer-events:none}
  #__ff{position:fixed;right:28px;top:84px;padding:8px 16px;background:#1f5eff;color:#fff;font:700 24px -apple-system,Helvetica,Arial,sans-serif;border-radius:10px;z-index:2147483647;display:none;pointer-events:none}`;
  const render = () => {
    if (!document.documentElement) return;
    let st = document.getElementById('__st'); if (!st) { st = document.createElement('style'); st.id = '__st'; document.documentElement.appendChild(st); }
    st.textContent = css;
    let s = document.getElementById('__sub'); if (!s) { s = document.createElement('div'); s.id = '__sub'; document.documentElement.appendChild(s); }
    let f = document.getElementById('__ff'); if (!f) { f = document.createElement('div'); f.id = '__ff'; f.textContent = '⏩ agent working · 4x'; document.documentElement.appendChild(f); }
    const t = sessionStorage.getItem('__sub') || '';
    s.textContent = t; s.style.display = t && !window.__hideSub ? 'block' : 'none';
    f.style.display = sessionStorage.getItem('__ff') ? 'block' : 'none';
  };
  window.__render = render;
  document.addEventListener('DOMContentLoaded', render); render();
  setInterval(render, 150);
})();
"""


def card(body):
    return f"""<!doctype html><html><head><meta charset=utf-8><style>
body{{margin:0;width:1920px;height:1080px;background:#f6f5f2;color:#1b1d22;font-family:-apple-system,Helvetica,Arial,sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center}}
h1{{font-size:88px;margin:0 0 14px;letter-spacing:-2px}} .tag{{font-size:38px;color:#6b7079;margin-bottom:54px}}
.pb{{font-size:44px;line-height:1.75}} .pb b{{color:#c2382b}}
.row{{display:flex;gap:22px;align-items:stretch}} .box{{background:#fff;border:3px solid #1b1d22;border-radius:18px;padding:22px 28px;font-size:32px;min-width:250px}}
.box small{{display:block;font-size:24px;color:#6b7079;margin-top:10px;line-height:1.4}} .arrow{{align-self:center;font-size:52px;color:#1f5eff}}
.m{{border-color:#1f5eff;background:#e8eeff}} .c{{border-color:#12805c;background:#e3f4ec}}</style></head><body>{body}</body></html>"""


CARD_PROBLEM = card("""<h1>Listing Pilot</h1><div class=tag>For the one-person Amazon shop</div>
<div class=pb>A phone photo on a cluttered table.<br>Amazon wants: <b>pure white</b> main image &middot; title <b>&le; 75</b> characters<br>
no <b>"eco-friendly"</b>, <b>"non-toxic"</b>, <b>"full refund"</b> &hellip;<br>One mistake &rarr; suppressed listing.</div>""")
CARD_PROMISE = card("""<h1>Listing Pilot</h1><div class=tag>One product photo in. A compliance-checked Amazon listing out.</div>
<div class=pb>Meta's models see, cut and re-shoot.<br>Plain code checks decide what passes.<br>The agent repairs <b>only what failed</b>.</div>""")
CARD_ARCH = card("""<div style="font-size:54px;font-weight:700;margin-bottom:34px">How it works</div>
<div class=row><div class=box>Seller photo<small>+ notes in any language</small></div><div class=arrow>&rarr;</div>
<div class="box m"><b>Muse Spark</b><small>product facts, props,<br>restricted claims flagged</small></div><div class=arrow>&rarr;</div>
<div class="box m"><b>SAM 3.1</b><small>mask &rarr; pure white<br>main image</small></div><div class=arrow>&rarr;</div>
<div class="box c"><b>Pixel checks</b><br><b>+ Spark review</b><small>fail &rarr; <b>Muse Image</b><br>studio re-shoot, loop</small></div></div>
<div style="height:30px"></div>
<div class=row><div class="box m"><b>Muse Spark</b><small>title, 5 bullets,<br>description, keywords</small></div><div class=arrow>&rarr;</div>
<div class="box c"><b>Rule engine</b><small>Amazon US rules;<br>only failures go back</small></div><div class=arrow>&rarr;</div>
<div class="box m"><b>Muse Image</b><small>lifestyle shots,<br>Spark checks the match</small></div><div class=arrow>&rarr;</div>
<div class=box><b>Package</b><small>images + JSON + CSV</small></div></div>
<div style="margin-top:46px;font-size:38px;font-weight:600">github.com/Dazzlar199/listing-pilot</div>
<div style="margin-top:8px;font-size:27px;color:#6b7079">MIT licensed &middot; built during the Meta Global AI Developer Hackathon, Oct 26 &ndash; Nov 4, 2026</div>""")

marks = []; sub_queue = []; cur_end = 0.0; fast = []; fast_on = None


def now(): return time.time() - T0


def tick(pg):
    while sub_queue and sub_queue[0][0] <= now():
        _, text = sub_queue.pop(0)
        try: pg.evaluate("t => { sessionStorage.setItem('__sub', t); window.__render && window.__render(); }", text)
        except Exception: pass


def sleep(pg, sec):
    end = time.time() + sec
    while time.time() < end: tick(pg); time.sleep(0.05)


def sleep_until_narr_done(pg):
    while now() < cur_end: tick(pg); time.sleep(0.05)


def ff(pg, on):
    """Mark a stretch where nobody talks and the agent works: badge on screen, sped up in the final cut."""
    global fast_on
    if on and fast_on is None:
        fast_on = now(); pg.evaluate("() => { sessionStorage.setItem('__ff','1'); sessionStorage.setItem('__sub',''); window.__render(); }")
    elif not on and fast_on is not None:
        pg.evaluate("() => { sessionStorage.removeItem('__ff'); window.__render(); }")
        if now() - fast_on > 1.5: fast.append((fast_on + 0.4, now() - 0.2))
        fast_on = None


def say(pg, key):
    global cur_end
    sleep_until_narr_done(pg); ff(pg, False)
    start = now(); marks.append((key, start))
    sents = re.split(r"(?<=[.!?:])\s+", LINES[key]); total = sum(len(s) for s in sents); t = start
    for s in sents:
        sub_queue.append((t, s)); t += DUR[key] * len(s) / total
    cur_end = start + DUR[key] + 0.45; tick(pg)


def log_has(pg, text):
    return text in pg.inner_text("#log")


def wait_event(pg, text, timeout=240):
    """Let the current line finish, then wait (fast-forwarded) until the agent log shows `text`."""
    sleep_until_narr_done(pg)
    end = time.time() + timeout
    while time.time() < end:
        tick(pg)
        if log_has(pg, text): ff(pg, False); return True
        if log_has(pg, "Listing package ready") or pg.locator(".ev.fail .s:text-is('error')").count():
            ff(pg, False); return False
        if now() >= cur_end: ff(pg, True)
        time.sleep(0.15)
    ff(pg, False); return False


def shot(pg, name, sel=None):
    pg.evaluate("() => { window.__hideSub = true; sessionStorage.removeItem('__ff'); window.__render(); }"); time.sleep(0.3)
    (pg.locator(sel) if sel else pg).screenshot(path=str(SHOTS / name))
    pg.evaluate("() => { window.__hideSub = false; window.__render(); }")


def scroll(pg, sel, block="start"):
    pg.evaluate("([s, b]) => document.querySelector(s).scrollIntoView({behavior:'smooth', block:b})", [sel, block])


with sync_playwright() as p:
    br = p.chromium.launch(executable_path=exe, headless=True)
    ctx = br.new_context(locale="en-US", viewport={"width": 1920, "height": 1080}, record_video_dir=str(W / "rec"),
                         record_video_size={"width": 1920, "height": 1080})
    ctx.add_init_script(INIT)
    T0 = time.time(); pg = ctx.new_page()
    pg.set_content(CARD_PROBLEM); say(pg, "problem"); sleep_until_narr_done(pg)
    pg.set_content(CARD_PROMISE); say(pg, "promise"); sleep_until_narr_done(pg)

    pg.goto(B); pg.wait_for_selector("#samples button"); sleep(pg, 0.8)
    say(pg, "app"); sleep(pg, 4.0)
    pg.click("#samples button[data-s='candle']"); sleep(pg, 1.2)
    pg.locator("#notes").scroll_into_view_if_needed(); sleep_until_narr_done(pg)
    shot(pg, "01_input.png")
    pg.click("#go"); sleep(pg, 0.6); say(pg, "start")

    wait_event(pg, "phrase(s) Amazon restricts"); say(pg, "flagged")
    wait_event(pg, "SAM 3.1 segments"); say(pg, "sam")
    wait_event(pg, "reviews the composite")
    sleep_until_narr_done(pg)
    # repair loop or not: decided by what the live run does
    end = time.time() + 120
    while time.time() < end and not (log_has(pg, "Found:") or log_has(pg, "passes all checks")):
        tick(pg); ff(pg, True); time.sleep(0.15)
    ff(pg, False)
    repaired = log_has(pg, "Found:") and not log_has(pg, "on attempt 1")
    if repaired:
        say(pg, "repair"); shot(pg, "02_agent_log.png", ".grid2 > .card:first-child")
        wait_event(pg, "passes all checks"); say(pg, "mainpass")
    else:
        say(pg, "norepair"); wait_event(pg, "passes all checks")
    wait_event(pg, "Spark writes the title"); say(pg, "copy")
    wait_event(pg, "Muse Image stages"); say(pg, "lifestyle")
    if not repaired: shot(pg, "02_agent_log.png", ".grid2 > .card:first-child")
    wait_event(pg, "Listing package ready")
    pg.wait_for_selector("#result .lt", timeout=60000); sleep(pg, 0.8)
    shot(pg, "03_result.png")
    say(pg, "result"); sleep(pg, 2.0)
    pg.click("#result .thumbs img[data-i='1']"); sleep(pg, 3.0)
    pg.click("#result .thumbs img[data-i='2']"); sleep(pg, 3.0)
    pg.click("#result .thumbs img[data-i='0']"); sleep(pg, 1.0)
    scroll(pg, "#result .bul", "center"); sleep_until_narr_done(pg)
    say(pg, "report"); scroll(pg, "#result .rep", "start"); sleep(pg, 1.5)
    shot(pg, "04_report.png", "#result")
    sleep(pg, 4.0); scroll(pg, "#result a.dl", "center"); sleep(pg, 1.5)
    pg.hover("#result a.dl"); sleep(pg, 1.0)
    href = pg.get_attribute("#result a.dl", "href")
    try:
        from urllib.parse import urljoin
        (W / "listing_package.zip").write_bytes(pg.request.get(urljoin(B + "/", href or "")).body())
    except Exception as e:
        print("package fetch skipped:", repr(e)[:120], href)
    sleep_until_narr_done(pg)
    run_dir = pg.evaluate("() => document.querySelector('#result a.dl').getAttribute('href')")
    pg.set_content(CARD_ARCH); say(pg, "arch"); sleep_until_narr_done(pg); sleep(pg, 1.0)
    total = now()
    vid = pg.video.path(); ctx.close(); br.close()

print("recorded", round(total, 1), "s", vid, "repaired:", repaired, "package:", run_dir)
json.dump({"marks": marks, "fast": fast, "total": total, "video": str(vid), "repaired": repaired, "package": run_dir},
          open(W / "marks.json", "w"), indent=1)

# ---- final cut: speed up the fast-forward stretches, place narration at the mapped times
segs, t = [], 0.0
for a, b in fast:
    if a > t: segs.append((t, a, 1.0))
    segs.append((a, b, FAST)); t = b
segs.append((t, total, 1.0))


def mapped(x):
    out = 0.0
    for a, b, s in segs:
        if x >= b: out += (b - a) / s
        else:
            out += max(0.0, x - a) / s; break
    return out


vf = "".join(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{s}[v{i}];" for i, (a, b, s) in enumerate(segs))
vf += "".join(f"[v{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0,fps=30[vout];"
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(vid)]
for k, _ in marks: cmd += ["-i", str(W / f"{k}.wav")]
af = "".join(f"[{i + 1}:a]adelay={int(mapped(t0) * 1000)}|{int(mapped(t0) * 1000)}[a{i}];" for i, (k, t0) in enumerate(marks))
af += "".join(f"[a{i}]" for i in range(len(marks))) + f"amix=inputs={len(marks)}:normalize=0,apad[aout]"
final = mapped(total)
cmd += ["-filter_complex", vf + af, "-map", "[vout]", "-map", "[aout]", "-t", f"{final:.2f}", "-c:v", "libx264", "-preset", "slow",
        "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(OUTMP4)]
subprocess.run(cmd, check=True)
print("wrote", OUTMP4, "final length", round(final, 1), "s")
