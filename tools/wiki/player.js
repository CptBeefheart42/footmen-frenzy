const trace = db.trace;
const categoryNames = {heroes:"Heroes", units:"Units & summons", buildings:"Buildings", abilities:"Abilities",
  items:"Items", effects:"Buffs & effects", visuals:"Visual effects", upgrades:"Upgrades", encounters:"Colossal waves"};
const typeNames = {heroes:"Hero", units:"Unit", buildings:"Building", abilities:"Ability", items:"Item",
  effects:"Effect", upgrades:"Upgrade", destructibles:"Destructible", doodads:"Doodad"};
const liveKeys = new Set(Object.keys(trace.via));
const supportKeys = new Set(trace.support);
const incoming = new Map();
const requirements = new Map();
const visualUses = new Map();
for(const [model,owners] of Object.entries(trace.visuals)){
  for(const key of owners)add(visualUses,key,model);
}
for (const from of liveKeys) {
  for (const edge of trace.edges[from] || []) {
    if (!edge.reference_only && liveKeys.has(edge.to)) add(incoming,edge.to,{from,...edge});
    if (edge.reference_only) add(requirements,edge.to,{from,...edge});
  }
}
let directory = "heroes", filter = "", directoryPage = 0;
const pageSize = 48;
const heroForms=new Map(), mainHero=new Map(), hiddenRecords=new Set();
for(const key of liveKeys){
  const o=db.objects[key];
  const debugButton=trace.roots[key]?.every(([reason,source])=>reason==="Trigger selection table"&&source.includes("FFDebugHireButton"));
  if(debugButton || (o.group==="heroes" && o.fields.some(f=>f[0]==="unsf" && /\bno\s*mute\b/i.test(f[3])))){
    hiddenRecords.add(key); continue;
  }
  if(o.group==="heroes")add(heroForms,displayName(key),key);
}
for(const [name,forms] of heroForms){
  const main=forms.find(k=>trace.roots[k]?.some(([why])=>why==="Hero selection roster")) ||
    forms.find(k=>trace.roots[k]?.length) || forms[0];
  mainHero.set(name,main);
}

function formLabel(key){
  if(mainHero.get(displayName(key))===key)return "Main form";
  const sources=(incoming.get(key)||[]).filter(e=>/form unit/i.test(e.label));
  const source=sources.find(e=>/alternate/i.test(e.label))||sources[0];
  const suffix=db.objects[key].fields.find(f=>f[0]==="unsf")?.[3]?.trim().replace(/^\(|\)$/g,"");
  if(source)return [displayName(source.from),levelCaption(source.levels)||suffix||source.label.replace(" Unit","")].join(" · ");
  return suffix || provenance(key) || "Alternate form";
}
function compactForms(keys){
  return '<div class="form-links">'+keys.filter(k=>!hiddenRecords.has(k)).map(k=>
    '<a href="#'+esc(encodeURIComponent(k))+'" '+(k===active?'aria-current="page"':'')+'>'+esc(formLabel(k))+'</a>').join("")+'</div>';
}

function displayName(key) {
  const o = db.objects[key];
  const name = o.name.trim().replace(/\|[nN]/g," ");
  return !name || name === o.id || /^WESTRING_/i.test(name) ? (typeNames[o.group]||"Map object") : name;
}
function portrait(key) {
  const o = db.objects[key];
  let image = o.art;
  let note = displayName(key);
  if (!image) {
    const provider = (incoming.get(key)||[]).find(e=>db.objects[e.from].art);
    if (provider) {
      image = db.objects[provider.from].art;
      note = "Associated artwork from " + displayName(provider.from);
    }
  }
  if (image && db.portraits[image]) {
    return '<img class="portrait" alt="" loading="lazy" title="'+esc(note)+'" src="data:image/webp;base64,'+db.portraits[image]+'">';
  }
  return '<span class="portrait" aria-hidden="true" title="No assigned portrait">'+esc(displayName(key)[0])+'</span>';
}
function card(key,caption="",url=key) {
  return '<a class="portrait-link" href="#'+esc(encodeURIComponent(url))+'">'+portrait(key)+
    '<span><strong>'+esc(displayName(key))+'</strong>'+(caption?'<small>'+esc(caption)+'</small>':'')+'</span></a>';
}
function directoryGroups(group) {
  const byName = new Map();
  if(group==="visuals"){
    for(const model of Object.keys(trace.visuals))add(byName,modelName(model),model);
    return [...byName].sort(([a],[b])=>a.localeCompare(b));
  }
  const keys = group==="encounters" ? Object.keys(trace.waves).filter(k=>trace.waves[k].boss) : liveKeys;
  for (const key of keys) {
    const o=db.objects[key];
    if (!o || hiddenRecords.has(key) || (group!=="encounters" && o.group!==group)) continue;
    if(group==="heroes" && mainHero.get(displayName(key))!==key)continue;
    add(byName,displayName(key),key);
  }
  return [...byName].sort(([a],[b])=>a.localeCompare(b));
}
function nav(group) {
  $("playerNav").innerHTML=Object.entries(categoryNames).map(([k,name])=>
    '<a href="#catalog/'+k+'" '+(k===group?'aria-current="page"':'')+'>'+esc(name)+'</a>').join("");
}
function catalogue(group) {
  directory=group;
  nav(group);
  detail.innerHTML='<div class="directory-head"><h1>'+esc(categoryNames[group])+'</h1>'+
    '<input id="playerFilter" aria-label="Search '+esc(categoryNames[group])+'" type="search" placeholder="Search '+esc(categoryNames[group].toLowerCase())+'"></div><div id="playerCards"></div>';
  const input=$("playerFilter");
  input.value=filter;
  const groups=directoryGroups(group);
  function redraw(){
    const matching=groups.filter(([name])=>name.toLowerCase().includes(filter.toLowerCase()));
    directoryPage=Math.min(directoryPage,Math.max(0,Math.ceil(matching.length/pageSize)-1));
    const start=directoryPage*pageSize;
    const cards=matching.slice(start,start+pageSize).map(([name,keys])=>{
      const url=keys.length>1?"variants/"+group+"/"+name:undefined;
      const caption=url?keys.length+" variants":"";
      return group==="visuals"?visualCard(keys[0],caption,url):card(keys[0],caption,url);
    });
    const buttons=matching.length>pageSize?'<div class="directory-foot"><button id="earlier">Previous</button><small>'+
      (start+1)+'–'+Math.min(start+pageSize,matching.length)+' of '+matching.length+'</small><button id="later">Next</button></div>':'';
    $("playerCards").innerHTML=cards.length?'<div class="cards">'+cards.join("")+'</div>'+buttons:'<p>No matching entries.</p>';
    if ($("earlier")) {
      $("earlier").disabled=directoryPage===0;
      $("later").disabled=start+pageSize>=matching.length;
      $("earlier").onclick=()=>{directoryPage--;saveDirectory();redraw()};
      $("later").onclick=()=>{directoryPage++;saveDirectory();redraw()};
    }
  }
  input.oninput=()=>{filter=input.value;directoryPage=0;saveDirectory();redraw()};
  redraw();
}
function provenance(key){
  const root=trace.roots[key]?.[0];
  if (root) return root[0];
  return trace.via[key] ? "From "+displayName(trace.via[key]) : "";
}
function levelCaption(levels) {
  if(!levels.length) return "";
  const sorted=[...new Set(levels)].sort((a,b)=>a-b);
  return (sorted.length===1?"Level ":"Levels ")+sorted.join(", ");
}
const commandGrid=["QWER","ASDF","ZXCV"];
function commandInfo(key){
  const {cast={},learn={}}=db.objects[key].command||{};
  const grid=commandGrid[cast.y]?.[cast.x];
  const hidden=cast.y<0 || cast.x<0;
  const slot=hidden?"":cast.key||grid||"";
  const labels=[];
  if(!hidden && grid && cast.key && grid!==cast.key)labels.push("Grid "+grid);
  if(learn.key)labels.push("Learn "+learn.key);
  const position=slot.length===1?"QWERASDFZXCV".indexOf(slot):-1;
  return {slot,caption:labels.join(" · "),label:cast.key?"Cast key":"Grid position",order:position>=0?position:grid?cast.y*4+cast.x:99};
}
function spellCards(links){
  return [...links].sort((a,b)=>commandInfo(a.to).order-commandInfo(b.to).order||displayName(a.to).localeCompare(displayName(b.to)))
    .map(e=>{
      const info=commandInfo(e.to),caption=[info.caption,levelCaption(e.levels)].filter(Boolean).join(" · ");
      const badge=info.slot?'<kbd title="'+info.label+'" aria-label="'+info.label+' '+esc(info.slot)+'">'+esc(info.slot)+'</kbd>':"";
      return '<a class="portrait-link" href="#'+esc(encodeURIComponent(e.to))+'">'+portrait(e.to)+'<span><strong>'+
        esc(displayName(e.to))+'</strong>'+(caption?'<small>'+esc(caption)+'</small>':'')+'</span>'+badge+'</a>';
    }).join("");
}
function relatedCards(links, direction, references=false) {
  const grouped=new Map();
  for(const edge of links){
    const key=direction==="from"?edge.from:edge.to;
    if(hiddenRecords.has(key)||(!liveKeys.has(key)&&!(references&&supportKeys.has(key)))) continue;
    if(edge.reference_only&&!references) continue;
    if(!grouped.has(key))grouped.set(key,new Set());
    for(const level of edge.levels)grouped.get(key).add(level);
  }
  return [...grouped].sort(([a,al],[b,bl])=>(al.size&&bl.size?Math.min(...al)-Math.min(...bl):0)||displayName(a).localeCompare(displayName(b)))
    .map(([k,levels])=>card(k,levelCaption([...levels]))).join("");
}
function cardSection(title,content){
  if(!content)return "";
  const cards=content.match(/<a class="portrait-link"[\s\S]*?<\/a>/g)||[];
  if(cards.length<=12)return '<h2>'+esc(title)+'</h2><div class="cards">'+content+'</div>';
  return '<h2>'+esc(title)+'</h2><div class="cards">'+cards.slice(0,8).join("")+'</div>'+
    details("Show "+(cards.length-8)+" more",'<div class="cards">'+cards.slice(8).join("")+'</div>');
}
function statGrid(pairs) {
  return '<div class="stat-grid">'+pairs.map(([label,value])=>'<div><small>'+esc(label)+'</small><b>'+esc(value)+'</b></div>').join("")+'</div>';
}
function baseStats(key){
  const o=db.objects[key], out=new Map(), levels=new Map();
  const cap=Number(o.stats.find(s=>s.field==="alev")?.value)||0;
  for(const s of o.stats){
    if(s.additional || (s.level && cap && s.level>cap))continue;
    if(!s.level)out.set(s.label,s.value);
    else {
      if(!levels.has(s.label))levels.set(s.label,new Map());
      levels.get(s.label).set(s.level,s.value);
    }
  }
  for(const t of db.tables){
    if(key!=="units/"+o.id)continue;
    const row=t.rows.find(r=>r.id?.value===o.id);
    if(!row)continue;
    for(const [field,label] of Object.entries(t.columns)){
      if(!field.startsWith("udg_")||field==="udg_base_type"||!row[field])continue;
      const aliases={"Armor":"Base armor","Base damage":"Attack 1 base damage","Attack cooldown":"Attack 1 cooldown (s)"};
      out.set(aliases[label]||label,row[field].value);
    }
  }
  const wave=trace.waves[key];
  if(wave?.boss){
    const b=wave.entries[0].base;
    for(const [label,value] of [["HP",b.hp_base],["Mana",b.mp_base],["Attack 1 base damage",b.dmg_base],["Base armor",b.armor],["Base bounty",b.bounty_base]])out.set(label,value);
  }
  const visible=[...out].filter(([name,v])=>Number(v)!==0 || name==="Base armor");
  let html=visible.length?'<h2>'+(wave?.boss?'Base stats':'Stats')+'</h2>'+statGrid(visible):"";
  if(levels.size){
    const ranks=[...new Set([...levels.values()].flatMap(m=>[...m.keys()]))].sort((a,b)=>a-b);
    const renderRows=rs=>table(["Stat",...ranks.map(n=>"Lv. "+n)],
      rs.map(([label,values])=>[esc(label),...ranks.map(n=>esc(values.get(n)??"—"))]));
    const hasValue=([,values])=>[...values.values()].some(v=>Number(v)!==0);
    const rows=[...levels].filter(hasValue), zero=[...levels].filter(r=>!hasValue(r));
    if(rows.length)html+='<h2>Values by level</h2>'+renderRows(rows);
    if(zero.length)html+=details("Zero-value fields",renderRows(zero));
  }
  const extra=o.stats.filter(s=>s.additional && !out.has(s.label) && (!cap || s.level<=cap));
  if(extra.length)html+=details("More balance values",table(["Stat","Level","Value"],extra.map(s=>[esc(s.label),s.level||"—",esc(s.value)])));
  return html;
}
function description(key){
  const o=db.objects[key], codes={units:"utub",items:"utub",abilities:"aub1",effects:"fube",upgrades:"gub1"};
  const group=key.split("/")[0], seen=new Set();
  let current=o, value="";
  while(current&&!seen.has(current.id)&&!value){
    seen.add(current.id);
    const field=[...current.fields].reverse().find(f=>f[0]===codes[group] && f[1]<=1 && f[3]);
    if(field)value=field[3];
    if(!value)for(const row of Object.values(current.stock).reverse()){
      value=row.Ubertip||row.Buffubertip||"";
      if(value)break;
    }
    current=db.objects[group+"/"+current.parent];
  }
  if(!value||value==="_")return "";
  value=String(value).replace(/\|c[\da-f]{8}|\|r/ig,"").replace(/\|n/ig,"\n").replace(/^"|"$/g,"");
  value=value.replace(/<(\w{4}),(\w+?)(\d+)(,%)?>/g,(_,id,col,rank,percent)=>{
    const k=(byID.get(id)||[]).find(k=>k.startsWith("abilities/"));
    if(!k)return "…";
    const s=db.objects[k].stats.find(s=>{
      const m=db.metadata.abilities?.[s.field];if(!m||s.level!==Number(rank))return false;
      const c=m.field==="Data"?"Data"+String.fromCharCode(64+Number(m.data)):m.field;
      return c.toLowerCase()===col.toLowerCase();
    });
    return s?String(percent?Math.round(Number(s.value)*100):s.value):"…";
  }).replace(/<[^>]+>/g,"…");
  return '<p class="deck">'+esc(value)+'</p>';
}
function wavePage(key) {
  const wave=trace.waves[key];
  if(!wave?.boss)return "";
  const base=wave.entries[0].base;
  let html="<h2>Colossal wave progression</h2>";
  if(wave.parity)html+="<p>Appears on "+wave.parity+"-numbered waves.</p>";
  if(wave.first&&wave.interval) html+="<p>Initial timer "+wave.first+" seconds. Repeat timer "+wave.interval+" seconds.</p>";
  if(wave.growth&&wave.scaled.length){
    html+="<p>The spawn calculation adds "+Number((100*wave.growth).toFixed(2))+"% of the base value per wave to "+
      wave.scaled.map(k=>({hp:"health",dmg:"damage",bounty:"bounty"}[k])).join(", ")+".</p>";
    const truncate=(n)=>Math.floor(n+1e-7);
    const heads=["Wave","Level",...wave.scaled.map(k=>({hp:"HP",dmg:"Base damage",bounty:"Base bounty"}[k]))];
    const rows=[];
    for(let n=1;n<=wave.max_wave;n++){
      if(wave.parity && (n%2===0)!==(wave.parity==="even"))continue;
      const level=wave.level_curve?wave.level_curve[0]+Math.min(wave.level_curve[1],Math.floor((n-1)/wave.level_curve[2])):base.level;
      rows.push([n,level,...wave.scaled.map(k=>truncate(base[k+"_base"]*(1+n*wave.growth)))]);
    }
    if(rows.length)html+=details("Wave scaling at the default difficulty",table(heads,rows),true);
  }
  return html;
}
function modelName(model){
  return db.models[model].path.split("\\").pop().replace(/\.(?:mdl|mdx)$/i,"")
    .replace(/([a-z])([A-Z])/g,"$1 $2").replace(/[_-]/g," ").trim();
}
function visualCard(model,caption="",url="visual/"+model){
  const uses=trace.visuals[model],owner=uses.find(k=>db.objects[k].art)||uses[0];
  return '<a class="portrait-link" href="#'+esc(encodeURIComponent(url))+'">'+portrait(owner)+'<span><strong>'+
    esc(modelName(model))+'</strong>'+(caption?'<small>'+esc(caption)+'</small>':'')+'</span></a>';
}
function visualPage(model){
  const owners=trace.visuals[model];
  return '<h1>'+esc(modelName(model))+
    '</h1>'+cardSection("Referenced by",owners.map(k=>card(k)).join(""));
}
function summonStats(key){
  let html="";
  for(const rule of trace.summon_rules[key]||[]){
    const values=Object.entries(rule.values);
    if(!values.length)continue;
    const levels=[...new Set(values.flatMap(([,v])=>Object.keys(v).map(Number)))].sort((a,b)=>a-b);
    const labels={hp:"Health",att_base:"Base damage",armor:"Armor",bounty:"Bounty",mp:"Mana"};
    html+='<h2>Stats at summoning</h2>'+table(["Stat",...levels.map(n=>"Lv. "+n)],
      values.map(([k,v])=>[esc(labels[k]||k.replaceAll("_"," ")),...levels.map(n=>esc(v[n]??"—"))]));
  }
  return html;
}
function playerObject(key) {
  const o=db.objects[key];
  if(hiddenRecords.has(key)){
    const main=mainHero.get(displayName(key));
    return '<h1>'+esc(displayName(key))+'</h1><p>This is a secondary map record.</p>'+
      (main?card(main,"Main hero"):"")+'<button type="button" id="inspectRecord">Inspect in Advanced</button>';
  }
  if(!liveKeys.has(key)&&!supportKeys.has(key)){
    const alternatives=[...liveKeys].filter(k=>db.objects[k].group===o.group&&displayName(k)===displayName(key));
    return '<h1>'+esc(displayName(key))+'</h1><p>This record has no traced gameplay path in this edition.</p>'+
      cardSection("In-game versions",alternatives.map(k=>card(k)).join(""))+
      '<p>'+link("catalog/heroes","Browse heroes")+' · <button type="button" id="inspectRecord">Inspect in Advanced</button></p>';
  }
  let html='<div class="profile">'+portrait(key)+'<div><small>'+esc(typeNames[o.group]||"Map object")+'</small><h1>'+esc(displayName(key))+'</h1></div>'+
    (o.fields.length?'<button type="button" id="editRecord" class="pencil" title="Edit map fields" aria-label="Edit map fields">✎</button>':'')+'</div>';
  const forms=heroForms.get(displayName(key))||[];
  if(o.group==="heroes" && forms.length>1)html+=compactForms([mainHero.get(displayName(key)),...forms.filter(k=>k!==mainHero.get(displayName(key)))]);
  if(o.group==="abilities"){
    const info=commandInfo(key);
    if(info.slot || info.caption)html+='<p class="command-line">'+(info.slot?info.label+' <kbd>'+esc(info.slot)+'</kbd> ':"")+esc(info.caption)+'</p>';
  }
  const desc=description(key);
  if(o.group!=="heroes")html+=desc;
  const outgoing=trace.edges[key]||[], byLabel=new Map();
  const priority=["Hero abilities","Abilities","Abilities on summon","Triggered abilities","Item abilities","Summoned Unit Type","Scripted summon","Possible summons"];
  const order=e=>priority.includes(e.label)?priority.indexOf(e.label):100;
  const displayed=new Set();
  for(const e of [...outgoing].sort((a,b)=>order(a)-order(b))){
    if(hiddenRecords.has(e.to)||e.reference_only||!liveKeys.has(e.to)||displayed.has(e.to))continue;
    displayed.add(e.to);add(byLabel,e.label,e);
  }
  for(const [label,links] of byLabel){
    if(/(?:normal|alternate) form unit/i.test(label)){
      html+='<h2>'+esc(label.replace(" Unit",""))+'</h2><div class="form-links">'+links.map(e=>
        link(e.to,[displayName(e.to),levelCaption(e.levels)].filter(Boolean).join(" · "))).join("")+'</div>';
    }else{
      const content=links.every(e=>db.objects[e.to].group==="abilities")?spellCards(links):relatedCards(links,"to");
      html+=cardSection(label==="Summoned Unit Type"?"Summons":label,content);
    }
  }
  const required=outgoing.filter(e=>e.reference_only&&/require/i.test(e.label));
  html+=cardSection("Requirements",relatedCards(required,"to",true));
  const back=incoming.get(key)||[];
  const summoners=back.filter(e=>db.objects[e.from].group==="abilities" && /summon/i.test(e.label));
  html+=cardSection("Summoned by",relatedCards(summoners,"from"));
  const owners=back.filter(e=>["heroes","units","buildings"].includes(db.objects[e.from].group));
  const usedBy=cardSection("Used by",relatedCards(owners,"from"));
  if(["abilities","effects"].includes(o.group))html+=usedBy;
  html+=summonStats(key)+baseStats(key)+wavePage(key);
  if(!["abilities","effects"].includes(o.group))html+=usedBy;
  html+=cardSection("Linked from",relatedCards(back.filter(e=>!owners.includes(e)&&!summoners.includes(e)),"from"));
  const requiredBy=(requirements.get(key)||[]).filter(e=>/require/i.test(e.label));
  html+=cardSection("Required by",relatedCards(requiredBy,"from",true));
  if(o.group==="heroes"&&desc)html+=details("In-game description",desc);
  const visuals=visualUses.get(key)||[];
  if(visuals.length)html+=details("Visual effects ("+visuals.length+")",'<div class="cards">'+visuals.map(m=>
    '<a class="portrait-link" href="#'+esc(encodeURIComponent("visual/"+m))+'">'+portrait(key)+'<strong>'+esc(modelName(m))+'</strong></a>').join("")+'</div>');
  if(liveKeys.has(key)){
    const trail=[key];
    while(trace.via[trail[0]])trail.unshift(trace.via[trail[0]]);
    const reasons=[...new Set((trace.roots[trail[0]]||[]).map(([reason])=>reason))];
    html+=details("Where it appears",'<p>'+reasons.map(esc).join(" · ")+'</p>'+
      (trail.length>1?'<p>'+trail.map(k=>link(k,displayName(k))).join(" → ")+'</p>':""),o.group==="abilities");
  }
  return html;
}
function playerRoute() {
  const [,group,...rest]=active.split("?")[0].split("/");
  if(db.objects[active]){
    nav(db.objects[active].group);
    detail.innerHTML=playerObject(active);
    if($("inspectRecord"))$("inspectRecord").onclick=()=>{$("advanced").checked=true;route()};
    if($("editRecord"))$("editRecord").onclick=()=>{
      $("advanced").checked=true;route();$("mapFields")?.focus();
    };
  } else if(["visual","model"].includes(active.split("/")[0])&&trace.visuals[active.slice(active.indexOf("/")+1)]){
    nav("visuals");detail.innerHTML=visualPage(active.slice(active.indexOf("/")+1));
  } else if(active.startsWith("variants/")&&categoryNames[group]){
    if(group==="heroes" && mainHero.has(rest.join("/"))){
      const main=mainHero.get(rest.join("/"));
      history.replaceState(null,"","#"+encodeURIComponent(main));route();return;
    }
    nav(group);const name=rest.join("/");
    const keys=directoryGroups(group).find(([n])=>n===name)?.[1]||[];
    detail.innerHTML='<h1>'+esc(name)+'</h1>'+
      '<div class="cards">'+keys.map((k,i)=>group==="visuals"?visualCard(k,"Variant "+(i+1)+" · "+displayName(trace.visuals[k][0])):
        card(k,"Variant "+(i+1)+" · "+provenance(k))).join("")+'</div>';
  } else {
    const params=directoryParams(active);
    filter=params.get("q")||"";directoryPage=Math.max(0,(parseInt(params.get("page"),10)||1)-1);
    catalogue(active.startsWith("catalog/")&&categoryNames[group]?group:"heroes");
  }
  renderTrail();
}

function directoryParams(key){return new URLSearchParams(key.split("?").slice(1).join("?"))}
function saveDirectory(){
  const params=new URLSearchParams();
  if(filter)params.set("q",filter);
  if(directoryPage)params.set("page",directoryPage+1);
  const key="catalog/"+directory+(params.size?"?"+params:"");
  active=key;
  history.replaceState({wikiTrail:[key]},"","#"+encodeURIComponent(key));
  renderTrail();
}
function entryLabel(key){
  if(key.startsWith("catalog/")){
    const group=key.split("/")[1].split("?")[0],q=directoryParams(key).get("q");
    return (categoryNames[group]||"Heroes")+(q?' search “'+q+'”':"");
  }
  if(key.startsWith("variants/"))return key.split("/").slice(2).join("/");
  if(db.objects[key]){
    const name=displayName(key),o=db.objects[key];
    if(o.group==="heroes" && mainHero.get(name)!==key && !hiddenRecords.has(key))return name+" · "+formLabel(key);
    const rank=(incoming.get(key)||[]).find(e=>/summoned unit type/i.test(e.label)&&e.levels.length);
    return name+(rank?" · "+levelCaption(rank.levels):"");
  }
  const model=key.slice(key.indexOf("/")+1);
  return db.models[model]?modelName(model):"Heroes";
}
function currentTrail(){
  const current=active||"catalog/heroes";
  const saved=history.state?.wikiTrail;
  if(Array.isArray(saved)&&saved.at(-1)===current)return saved;
  if(db.objects[current]){
    const path=[current];
    while(trace.via[path[0]])path.unshift(trace.via[path[0]]);
    return ["catalog/"+db.objects[path[0]].group,...path];
  }
  if(current.startsWith("variants/"))return ["catalog/"+current.split("/")[1],current];
  if(current.startsWith("visual/")||current.startsWith("model/"))return ["catalog/visuals",current];
  return [current.startsWith("catalog/")?current:"catalog/heroes"];
}
function renderTrail(){
  const old=$("guideTrail");if(old)old.remove();
  const path=currentTrail();
  if(path.length===1&&!filter)return;
  const html=path.map((k,i)=>i===path.length-1?'<span aria-current="page">'+esc(entryLabel(k))+'</span>':
    '<a data-trail-step="'+i+'" href="#'+esc(encodeURIComponent(k))+'">'+esc(entryLabel(k))+'</a>').join('<span aria-hidden="true"> › </span>');
  detail.insertAdjacentHTML("afterbegin",'<nav id="guideTrail" aria-label="Browsing path">'+html+'</nav>');
}
document.addEventListener("click",event=>{
  if($("advanced").checked || event.defaultPrevented || event.button!==0 || event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  const a=event.target.closest("a[href^='#']");
  if(!a)return;
  const key=decodeURIComponent(a.hash.slice(1))||"catalog/heroes";
  const path=currentTrail();
  const index=path.indexOf(key);
  const trail=a.hasAttribute("data-trail-step")?path.slice(0,Number(a.dataset.trailStep)+1):
    key.startsWith("catalog/")?[key]:index>=0?path.slice(0,index+1):[...path,key];
  event.preventDefault();
  if(trail.at(-1)===active)return;
  history.pushState({wikiTrail:trail},"","#"+encodeURIComponent(key));route();
});
function advancedTrace(key){
  const routeKeys=[key];let k=key;
  while(trace.via[k]){k=trace.via[k];routeKeys.unshift(k)}
  const text=liveKeys.has(key)?routeKeys.map(k=>link(k,displayName(k))).join(" → "):
    trace.parents.includes(key)?"Inherited parent of a traced record":trace.support.includes(key)?"Referenced requirement or skin":"No gameplay path found";
  const rules=[...(trace.waves[key]?.rules||[]),...(trace.summon_rules[key]||[]).map(r=>r.action)];
  const rootSource=src=>db.functions[src.split(":")[0]]?fnLink(src.split(":")[0]):esc(src);
  const audit=link("review","Reachability and asset review");
  return '<p>'+audit+'</p>'+details("Gameplay trace",'<p>'+text+'</p>'+((trace.roots[k]||[]).map(([why,src])=>'<div>'+esc(why)+' · '+rootSource(src)+'</div>').join(""))+
    (rules.length?'<p>Scaling rules · '+[...new Set(rules)].map(fnLink).join(" · ")+'</p>':""),true);
}
function reviewPage() {
  const all=Object.entries(db.objects),parents=new Set(trace.parents),support=new Set(trace.support);
  const unused=all.filter(([k,o])=>o.defined&&!liveKeys.has(k)&&!parents.has(k)&&!support.has(k));
  const imports=Object.entries(db.imports||{}), unmatched=imports.filter(([,uses])=>!uses.length);
  const noArt=[...liveKeys].filter(k=>categoryNames[db.objects[k].group]&&!db.objects[k].art);
  return '<h1>Reachability and asset review</h1><p>Static paths begin at placements, production and selection tables, or reachable trigger calls. Dynamic construction, mode checks and art loaded by convention require review before changing a map.</p>'+
    details("Map records without a traced path ("+unused.length+")",table(["Record","Type","ID"],unused.map(([k,o])=>[link(k,displayName(k)),esc(o.group),esc(o.id)])))+
    details("Inherited parents and supporting references", [...new Set([...parents,...support])].sort().map(k=>link(k,displayName(k))).join(" · "))+
    details("Imports with no traced reference ("+unmatched.length+" of "+imports.length+")",table(["Import"],unmatched.map(([p])=>[esc(p)])))+
    details("Imports with references",table(["Import","Referenced by"],imports.filter(([,uses])=>uses.length).map(([p,uses])=>[esc(p),uses.map(k=>entries.has(k)?link(k,entries.get(k).name):esc(k)).join(" · ")])))+
    details("Objects without their own decoded portrait ("+noArt.length+")",noArt.map(k=>link(k,displayName(k))).join(" · "))+
    details("Unresolved object relationships",table(["Owner","Field","Target"],trace.unresolved.map(([k,f,id])=>[link(k,displayName(k)),esc(f),esc(id)])))+
    details("Dynamic creation arguments",table(["Function","Line","Argument"],trace.dynamic.map(([n,l,v])=>[fnLink(n),l,esc(v)])));
}
$("advanced").onchange=()=>{route()};
