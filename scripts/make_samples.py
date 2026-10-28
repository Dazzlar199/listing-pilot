"""Generate seller-style sample photos with Muse Image (so the demo uses assets we own)."""
import base64, io, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.env import load_env
load_env()
from app.meta import _client, IMAGE_MODEL
from PIL import Image

SAMPLES = {
    "mug": "Casual smartphone photo taken by a small shop owner: a handmade speckled cream ceramic coffee mug "
           "with a wide handle on a cluttered wooden kitchen table, a few coffee beans and a spoon next to it, "
           "warm window light, slightly off-center, no text, no logos",
}
out = Path("samples"); out.mkdir(exist_ok=True)
for name, prompt in SAMPLES.items():
    if len(sys.argv) > 1 and name not in sys.argv[1:]: continue
    r = _client().images.generate(model=IMAGE_MODEL, prompt=prompt, n=1, size="1024x1024", response_format="b64_json",
                                  extra_body={"reasoning_strength": "low"})
    img = Image.open(io.BytesIO(base64.b64decode(r.data[0].b64_json))).convert("RGB")
    img.save(out / f"{name}.jpg", quality=92)
    print(name, img.size)
