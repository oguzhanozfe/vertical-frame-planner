/* The original app validates the editor's raw JSON and runs the repository's project.py. */
"use strict";
const runtimeURL = new URL("./python/", self.location.href);
let boot;

async function initialize() {
  if (typeof self.loadPyodide !== "function") importScripts(new URL("pyodide.js", runtimeURL).href);
  const py = await self.loadPyodide({indexURL: runtimeURL.href, fullStdLib: false});
  if (py.version !== "0.29.4") throw Error("Unexpected bundled Python runtime version.");
  await Promise.all(["app.py","project.py","providers.py","example.json"].map(async name => {
    const response = await fetch(new URL(name, self.location.href));
    if (!response.ok) throw Error("Cannot load " + name + " (HTTP " + response.status + ").");
    py.FS.writeFile("/home/pyodide/" + name, new Uint8Array(await response.arrayBuffer()));
  }));
  py.runPython(`
import app
import json
sample_source = app.read_json((app.ROOT / "example.json").read_bytes())

def same_json(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_json(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_json(x, y) for x, y in zip(a, b))
    if type(a) in (int, float) and type(b) in (int, float):
        return a == b
    return type(a) is type(b) and a == b

def browser_report(raw):
    try:
        source = app.read_json(raw.encode("utf-8"))
        report = app.calculate(source)
        return json.dumps({"report_text": json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
                           "matches_example": same_json(source, sample_source)}, ensure_ascii=False)
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as exc:
        return json.dumps({"error": str(exc) or "Invalid input."})
`);
  return py.globals.get("browser_report");
}

self.onmessage = async ({data}) => {
  const {id, action, raw} = data;
  try {
    if (action !== "ready" && action !== "analyze") throw Error("Unknown report operation.");
    if (action === "analyze" && (typeof raw !== "string" || raw.length > 262144))
      throw Error("Choose JSON under 256 KiB.");
    boot ||= initialize().catch(error => { boot = undefined; throw error; });
    const calculate = await boot;
    if (action === "ready") { self.postMessage({id, result: true}); return; }
    const answer = JSON.parse(calculate(raw));
    if (answer.error) throw Error(answer.error);
    self.postMessage({id, result: answer});
  } catch (error) {
    self.postMessage({id, error: error.message || String(error)});
  }
};
