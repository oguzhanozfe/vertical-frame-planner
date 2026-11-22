"""Build a serverless report workspace using the repository's original Python and diagram."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import sys


DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parent
SEMANTIC = """<section id="live-model" class="panel"><h2>Find report rows by meaning</h2>
<p>Describe what you want to review. MiniLM compares your focus with up to 16 findings on this device.
The first search downloads the model.</p>
<label for="semantic-focus">Review focus</label>
<div class="semantic-controls"><input id="semantic-focus" maxlength="600" placeholder="What matters in this report?">
<button id="semantic-run" type="button" class="primary">Find matching findings</button></div>
<p id="semantic-status" role="status"></p><div id="semantic-results"></div></section>"""

STYLE = """
#demo-runtime{font-size:13px;color:#47594f;margin:.45rem 0 1rem}
#live-model{margin-top:14px}#live-model p{font-size:14px;line-height:1.5}
#live-model label{font-size:14px;font-weight:650}#semantic-status:empty{display:none}
.semantic-controls{display:flex;flex-wrap:wrap;gap:8px;margin-top:5px}
#semantic-focus{flex:1 1 220px;min-width:0;font:inherit;background:#fff;border:1px solid #879b8f;border-radius:4px;padding:8px}
#semantic-results .card{margin:10px 0;padding:10px;border-top:1px solid #ccd6ca;overflow-wrap:anywhere}
#semantic-results small{display:block;color:#46594f;margin:4px 0}
tr.inspected td{background:#fff0c8}tr.inspected:focus{outline:2px solid #855a1d;outline-offset:-2px}
#model a{color:#315640}.actions{flex-wrap:wrap}
"""


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("The source template changed near: " + old[:70])
    return text.replace(old, new)


def recorded_sample(source_bytes):
    path = DEMO / "model-example.json"
    if not path.is_file():
        return None
    row = json.loads(path.read_text("utf-8-sig"))
    if not isinstance(row, dict) or row.get("source_sha256") != hashlib.sha256(source_bytes).hexdigest():
        print("Ignoring recorded commentary because the original input changed.", file=sys.stderr)
        return None
    if not all(isinstance(row.get(k), str) and row[k].strip() for k in ("model", "text")):
        raise ValueError("Recorded commentary must identify the model and include its text.")
    return {"model": row["model"], "text": row["text"], "source_sha256": row["source_sha256"]}


def static_page(web, slug):
    page = (web / "index.html").read_text("utf-8")
    page = once(page, 'href="/style.css"', 'href="./style.css"')
    page = once(page, 'src="/diagram.js"', 'src="./diagram.js"')
    page = once(page, '<script src="/ui.js" defer></script>',
                '<script src="./browser.js" defer></script><script src="./ui.js" defer></script>'
                '<script type="module" src="./semantic.js"></script>')
    page = once(page, '<button id="download">', '<button id="download" disabled>')
    page = once(page, '</nav>', '</nav><p id="demo-runtime" role="status">Opening the bundled report…</p>')
    page = once(page, '<button id="run" class="primary">',
                '<button id="demo-reset" type="button" disabled>Load example</button><button id="run" class="primary" disabled>')
    page = once(page, '<table><thead>', '<table aria-label="Computed findings"><thead>')
    older = re.search(r'<details id="model">.*?</details>', page, flags=re.S)
    if not older:
        raise ValueError("Missing model review panel")
    repo = "https://github.com/oguzhanozfe/" + slug
    panel = (SEMANTIC + '<details id="model"><summary>Recorded sample review</summary><p id="modelHint"></p>'
             '<p id="comment" aria-live="polite"></p><p><a href="' + html.escape(repo) +
             '#connect-a-model">Run the workspace locally for a new generative review ↗</a></p></details>')
    return once(page, older[0], panel)


def native_ui(text):
    # Reuse the original findings/metrics rendering and per-project diagram hook.
    marker = "async function analyze(review) {"
    if text.count(marker) != 1 or "window.drawProjectView(view, report, currentInput)" not in text:
        raise ValueError("Update the static UI adapter for the current project UI.")
    return text[:text.index(marker)] + """
window.firstDemo.attach({
  draw(input, report) { currentInput = input; show(report); },
  error: showError,
  tab
});
"""


def build(out):
    out = out.resolve()
    web = ROOT / "web"
    if out in {ROOT, DEMO, web}:
        raise ValueError("Choose an output folder separate from the source.")
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    import app

    ui = (web / "ui.js").read_text("utf-8")
    name = re.search(r'link\.download="(([a-z0-9-]+)-report\.json)"', ui)
    if not name:
        raise ValueError("The project needs its native report filename.")
    raw = (ROOT / "example.json").read_bytes()
    sample = app.read_json(raw)
    info = {"input": sample, "report": app.calculate(sample), "recorded": recorded_sample(raw), "filename": name[1]}
    for filename in ("app.py", "project.py", "providers.py", "example.json"):
        shutil.copyfile(ROOT / filename, out / filename)
    for filename in ("worker.js", "browser.js", "semantic.js"):
        shutil.copyfile(DEMO / filename, out / filename)
    shutil.copyfile(web / "diagram.js", out / "diagram.js")
    (out / "style.css").write_text((web / "style.css").read_text("utf-8") + STYLE, encoding="utf-8")
    (out / "index.html").write_text(static_page(web, name[2]), encoding="utf-8")
    (out / "ui.js").write_text(native_ui(ui), encoding="utf-8")
    (out / "demo-data.json").write_text(json.dumps(info, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    (out / ".nojekyll").touch()
    print(f"Built {name[2]} at {out}")


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    build(parser.parse_args().out)
