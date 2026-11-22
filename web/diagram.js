/* Standalone browser view for the computed project report. */
window.drawProjectView = function (host, report, input) {
  "use strict";
  function el(tag, text, css) {
    const item = document.createElement(tag);
    if (text != null) item.textContent = String(text);
    if (css) item.style.cssText = css;
    return item;
  }
  const figure = el("figure", null, "box-sizing:border-box;margin:12px 0 16px;padding:12px 14px;border-radius:9px;background:#172329;color:#f4f5f2;max-height:210px;overflow:auto;font:13px/1.35 system-ui,sans-serif;text-align:left");
  const head = el("figcaption", "Portrait safe-area preview", "font-size:15px;font-weight:700;letter-spacing:-.015em;color:#a5d8ff;margin-bottom:7px");
  figure.append(head);
  host.replaceChildren(figure);
  const rows = Array.isArray(report && report.rows) ? report.rows : [];
  if (!rows.length) {
    figure.append(el("p", "No findings to display.", "margin:0"));
    return;
  }

  function svg(tag,attrs) {
    const element = document.createElementNS("http://www.w3.org/2000/svg",tag);
    for (const [key,value] of Object.entries(attrs)) element.setAttribute(key,String(value));
    return element;
  }
  const selection = el("select",null,"max-width:100%;font:12px system-ui;background:#25363e;color:#f0f5f3;border:1px solid #556972;border-radius:4px;padding:3px 6px");
  selection.setAttribute("aria-label","Shot to preview");
  const available = rows.slice(0,60);
  available.forEach((row,index)=>{const opt=el("option",row.Shot);opt.value=String(index);selection.append(opt);});
  const problem = available.findIndex(row=>row["Outside safe area"]!=="None");
  selection.selectedIndex = Math.max(0,problem);
  const diagram = el("div"), caption = el("div",null,"color:#d7e2e0;font:11px/1.25 system-ui");
  const sourceWidth=input.source_width,sourceHeight=input.source_height,margin=input.safe_margin ?? .05;
  const annotations = new Map(input.shots.map(s=>[s.name.trim(),s]));
  function render() {
    const row=available[selection.selectedIndex];
    if (!row) return;
    const shot=annotations.get(row.Shot);
    const x=row["Left (px)"],y=row["Top (px)"],w=row["Width (px)"],h=row["Height (px)"];
    const plot=svg("svg",{viewBox:"0 0 "+sourceWidth+" "+sourceHeight,role:"img",width:"100%",height:100,"aria-label":"Source frame, portrait crop and annotated subject boxes for "+row.Shot});
    plot.style.display="block";
    function box(a,b,width,height,fill,stroke,dash) {
      const rect=svg("rect",{x:a,y:b,width,height,fill,stroke,"stroke-width":1.5,"vector-effect":"non-scaling-stroke"});
      if(dash)rect.setAttribute("stroke-dasharray",dash);
      plot.append(rect);
      return rect;
    }
    box(0,0,sourceWidth,sourceHeight,"#283942","#647881");
    box(x,y,w,h,"#39515c","#a5d8ff");
    box(x+w*margin,y+h*margin,w*(1-2*margin),h*(1-2*margin),"none","#c0dfca","4 3");
    for(const subject of (shot?.subjects || []).slice(0,30)) {
      const rect=box(subject.x,subject.y,subject.width,subject.height,"none","#ffba91");
      const title=svg("title",{}); title.textContent=subject.name; rect.append(title);
    }
    diagram.replaceChildren(plot);
    caption.textContent="Blue: crop · dashed: safe area · orange: subjects. Outside safe area: "+row["Outside safe area"]+". Display limits: 60 shots, 30 boxes per shot.";
  }
  selection.addEventListener("change",render);
  figure.append(selection,diagram,caption);
  render();

};
