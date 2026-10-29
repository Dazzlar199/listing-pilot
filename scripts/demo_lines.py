"""Narration lines for the demo video (key -> text). Used by demo_tts.py and record_demo.py.
'repair' or 'norepair' is spoken depending on whether the live run rejects the first main image."""
LINES = {
 "problem": "Selling on Amazon as a one-person shop starts with a phone photo on a cluttered table. But Amazon wants a pure white main image, a title under 75 characters, and no restricted claims like eco-friendly or non-toxic. Get one wrong, and the listing can be suppressed.",
 "promise": "Listing Pilot turns that one photo into a compliance-checked listing package. Meta's models do the seeing, the cutting, and the re-shooting. Plain code checks decide what passes, and the agent repairs only what failed.",
 "app": "This is the app, running live on the Meta Model API. I pick the candle sample: a photo on a messy dresser, and seller notes written in Korean, the way many small sellers actually write them.",
 "start": "I click Build my listing. Muse Spark reads the photo and the notes. It separates the product from the props, and lists what the photo cannot prove.",
 "flagged": "The notes say eco-friendly, non-toxic, Etsy bestseller, and full refund. Amazon restricts all four, so the agent flags them for the seller and keeps them out of the copy.",
 "sam": "Next, SAM 3.1 segments the candle jar. The pipeline fills enclosed parts that SAM leaves out, like the wax inside the jar, and places the product on pure white at the right fill ratio.",
 "repair": "Muse Spark reviews the composite against the original photo, and rejects it. So Muse Image re-shoots the product as a clean studio packshot, SAM cuts it out again, and the loop repeats.",
 "norepair": "Muse Spark reviews the composite against the original photo, next to pixel checks for a pure white border and product fill.",
 "mainpass": "This time the pixel checks and the visual review agree, so the main image is accepted.",
 "copy": "Now Spark writes the title, five bullets, the description, and search terms. A rule engine checks them against Amazon's published rules. Any violation goes back to the model, and only that part is rewritten.",
 "lifestyle": "Muse Image stages two lifestyle shots from the cut-out. Spark checks that the product still matches the seller's photo, and regenerates it if it drifted.",
 "result": "Here is the result. A white background main image, two lifestyle images, and copy that uses the seller's real specs, the eight ounce jar, soy wax, and forty five hour burn, with no restricted claims.",
 "report": "Below it: what the agent caught and fixed, and a compliance report for each rule. The seller downloads one package, with the images, a JSON file, and a CSV ready for a bulk upload.",
 "arch": "Under the hood: Muse Spark for understanding, review, and copy. SAM 3.1 for segmentation. Muse Image for studio repair and lifestyle shots. Deterministic checks are the source of truth. Listing Pilot is open source and MIT licensed, built during the Meta Global AI Developer Hackathon.",
}
