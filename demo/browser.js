/* Transport and review controls specific to the serverless browser build. */
(() => {
  "use strict";
  const el = id => document.getElementById(id);
  let worker, sequence = 0, version = 0, suggestionReport, source, downloadText, meta;
  const pending = new Map();
  const runtime = message => { el("demo-runtime").textContent = message; };

  function resetWorker(message) {
    if (worker) worker.terminate();
    worker = undefined;
    runtime("The local Python runtime stopped. Run the analysis again to reload it.");
    for (const {reject, timer} of pending.values()) { clearTimeout(timer); reject(Error(message)); }
    pending.clear();
  }

  function request(action, raw) {
    if (!worker) {
      runtime("Loading Python on this device. You can already inspect the bundled example.");
      worker = new Worker(new URL("./worker.js", document.baseURI));
      worker.onerror = () => resetWorker("The browser could not start the Python worker.");
      worker.onmessageerror = () => resetWorker("The browser could not read the Python result.");
      worker.onmessage = ({data}) => {
        const call = pending.get(data.id);
        if (!call) return;
        pending.delete(data.id); clearTimeout(call.timer);
        if (Object.prototype.hasOwnProperty.call(data,"error")) {
          if (call.action === "ready") runtime("Python could not start. Check the connection and run the analysis to retry.");
          call.reject(Error(data.error)); return;
        }
        runtime("Python is ready. Custom data is analyzed on this device.");
        call.resolve(data.result);
      };
    }
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => resetWorker("The local calculation timed out. Try a smaller input."), 180000);
      pending.set(id, {resolve, reject, timer, action});
      try { worker.postMessage({id, action, raw}); }
      catch (error) { clearTimeout(timer); pending.delete(id); reject(error); }
    });
  }

  function displayValue(value) {
    if (value === null) return "—";
    return typeof value === "object" ? JSON.stringify(value) : String(value);
  }

  function prepareRows(report) {
    const trs = document.querySelectorAll("tbody tr");
    const records = [], candidates = [];
    report.rows.forEach((row, index) => {
      const id = "row-" + (index + 1);
      trs[index].tabIndex = -1;
      trs[index].dataset.evidenceId = id;
      records.push({id, values: row});
      const fields = Object.entries(row).filter(([, v]) => v != null && v !== "");
      const action = fields.slice(0, 2).map(([key,value]) => key + ": " + displayValue(value)).join(" · ");
      candidates.push({id, action: action || "Finding " + (index + 1), evidence_ids: [id]});
    });
    suggestionReport = {records, candidates};
    window.dispatchEvent(new Event("demoreviewchange"));
  }

  window.getDemoReview = () => suggestionReport ? {report: suggestionReport, source} : null;
  window.inspectDemoCandidate = id => {
    const row = Array.from(document.querySelectorAll("tbody tr")).find(tr => tr.dataset.evidenceId === id);
    if (!row) return;
    document.querySelector("tr.inspected")?.classList.remove("inspected");
    row.classList.add("inspected");
    row.focus({preventScroll: true});
    row.scrollIntoView({block:"center", inline:"nearest"});
  };

  async function attach(ui) {
    function draw(input, report, matchesExample, jsonText) {
      source = input;
      downloadText = jsonText || JSON.stringify(report, null, 2);
      ui.draw(input, report);
      prepareRows(report);
      const recorded = matchesExample && meta.recorded;
      el("comment").textContent = recorded ? recorded.text : "";
      el("modelHint").textContent = recorded
        ? "Precomputed with " + recorded.model + " on the bundled example."
        : (matchesExample ? "No verified recorded review is available for this example."
                          : "The recorded review applies only to the bundled example.");
      el("model").open = Boolean(recorded);
      el("download").disabled = false;
    }

    el("reportTab").onclick = () => ui.tab(false);
    el("inputTab").onclick = () => ui.tab(true);
    el("run").onclick = async () => {
      const epoch = ++version, raw = el("source").value;
      el("run").disabled = true; ui.error("");
      try {
        const result = await request("analyze", raw);
        if (epoch !== version) return;
        draw(JSON.parse(raw.replace(/^\uFEFF/, "")), JSON.parse(result.report_text), result.matches_example, result.report_text);
        ui.tab(false);
      } catch (error) { if (epoch === version) ui.error(error.message); }
      finally { if (epoch === version) el("run").disabled = false; }
    };
    el("source").addEventListener("input", () => { ++version; el("run").disabled = false; });
    el("file").onchange = async event => {
      const file = event.target.files[0];
      if (!file) return;
      const epoch = ++version;
      try {
        if (file.size > 262144) throw Error("Choose a JSON file under 256 KiB.");
        const text = await file.text();
        if (epoch === version) { el("source").value = text; ui.error(""); }
      } catch (error) { if (epoch === version) ui.error(error.message); }
      finally { if (epoch === version) el("run").disabled = false; event.target.value = ""; }
    };
    el("demo-reset").onclick = () => {
      if (!meta) return;
      ++version; el("source").value = JSON.stringify(meta.input, null, 2); el("run").disabled = false;
      ui.error(""); draw(meta.input, meta.report, true); ui.tab(false);
    };
    el("download").onclick = () => {
      if (!downloadText) return;
      const url = URL.createObjectURL(new Blob([downloadText], {type:"application/json"}));
      const link = document.createElement("a"); link.href = url; link.download = meta.filename;
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    try {
      const response = await fetch("./demo-data.json");
      if (!response.ok) throw Error("The bundled example could not be loaded. Reload the page.");
      meta = await response.json();
      el("source").value = JSON.stringify(meta.input, null, 2);
      draw(meta.input, meta.report, true); el("provider").textContent = "Browser demo";
      el("run").disabled = false; el("demo-reset").disabled = false; document.body.dataset.ready = "true";
      setTimeout(() => request("ready").catch(() => {}), 0);
    } catch (error) { ui.error(error.message); }
  }

  window.firstDemo = {attach};
})();
