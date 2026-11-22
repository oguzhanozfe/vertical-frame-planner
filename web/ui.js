"use strict";
const $ = s => document.querySelector(s);
let currentReport, currentInput, settings;
function node(tag, value) {
  const element = document.createElement(tag);
  element.textContent = value == null ? "—" : String(value);
  return element;
}
function showError(message) {
  $("#error").textContent = message; $("#error").hidden = !message;
}
function tab(input) {
  $("#editor").hidden = !input; $("#result").hidden = input;
  $("#inputTab").setAttribute("aria-pressed", input);
  $("#reportTab").setAttribute("aria-pressed", !input);
}
function show(report) {
  currentReport = report;
  $("#summary").textContent = report.summary;
  const cards = Object.entries(report.metrics).map(([label,value]) => {
    const card = document.createElement("div"); card.className = "metric";
    card.append(node("b",value),node("small",label.replaceAll("_"," "))); return card;
  });
  $("#metrics").replaceChildren(...cards);
  const columns = Object.keys(report.rows[0] || {});
  const top = document.createElement("tr"); columns.forEach(key => top.append(node("th",key)));
  $("thead").replaceChildren(top);
  const lines = report.rows.map(row => {
    const tr = document.createElement("tr");
    columns.forEach(key => tr.append(node("td",typeof row[key] === "object" && row[key]!==null ? JSON.stringify(row[key]) : row[key])));
    return tr;
  });
  $("tbody").replaceChildren(...lines);
  const view = $("#diagram");
  view.replaceChildren();
  if (typeof window.drawProjectView === "function") window.drawProjectView(view, report, currentInput);
  view.hidden = !view.childNodes.length;
  $("#comment").textContent = report.model_review || "";
}
async function analyze(review) {
  const button = $(review ? "#review" : "#run"); button.disabled = true; showError("");
  try {
    const input = review ? currentInput : JSON.parse($("#source").value);
    const res = await fetch("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json","X-Access-Token":$("#access").value},body:JSON.stringify({input,review})});
    const payload = await res.json(); if (!res.ok) throw new Error(payload.error);
    currentInput = input; show(payload); tab(false);
  } catch(error) { showError(error.message); } finally { button.disabled = false; }
}
$("#inputTab").onclick=()=>tab(true); $("#reportTab").onclick=()=>tab(false);
$("#run").onclick=()=>analyze(false); $("#review").onclick=()=>analyze(true);
$("#file").onchange=async event=> {
  const file=event.target.files[0]; if (!file) return;
  if(file.size>262144){showError("Choose a JSON file under 256 KiB.");return;}
  $("#source").value=await file.text(); showError("");
};
$("#download").onclick=()=> {
  if(!currentReport) return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(currentReport,null,2)],{type:"application/json"}));
  const link=document.createElement("a"); link.href=url; link.download="vertical-frame-planner-report.json"; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
};
(async()=>{
  try {
    const res=await fetch("/api/example"); if(!res.ok) throw new Error("Could not load example");
    settings=await res.json(); currentInput=settings.input; $("#source").value=JSON.stringify(currentInput,null,2);
    $("#provider").textContent=settings.provider==="off" ? "Offline demo" : "Model: "+settings.provider;
    $("#review").disabled=settings.provider==="off"; $("#tokenLabel").hidden=!settings.access_token_required;
    if(settings.provider==="off") $("#modelHint").textContent="Set MODEL_PROVIDER and MODEL_ID on the server, then restart to enable model review.";
    show(settings.report); document.body.dataset.ready="true";
  } catch(error) { showError(error.message); }
})();
