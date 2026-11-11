'use strict';
const $=id=>document.getElementById(id);
const money=n=>new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP',maximumFractionDigits:0}).format(n);
const number=n=>new Intl.NumberFormat('en-GB').format(n);
const pct=n=>(100*n).toFixed(1)+'%';
const types={D:'Detached',S:'Semi-detached',T:'Terraced'};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let research,market,rows=[],page=0,requestVersion=0;
const cache=new Map();
const quantile=(xs,p)=>{const a=[...xs].sort((x,y)=>x-y);if(!a.length)return 0;const at=(a.length-1)*p,i=Math.floor(at);return a[i]+(a[Math.min(i+1,a.length-1)]-a[i])*(at-i)};

async function getJSON(url){const response=await fetch(url);if(!response.ok)throw Error('Could not load research data ('+response.status+').');return response.json()}

async function selectMarket(){
  const version=++requestVersion;
  market=research.markets.find(m=>m.name===$('market').value);
  $('sale-count').textContent='…';
  try{
    if(!cache.has(market.slug))cache.set(market.slug,await getJSON('data/'+market.slug+'.json'));
    if(version!==requestVersion)return;
    rows=cache.get(market.slug);page=0;
    $('market-description').textContent=market.name==='Linslade'?'Linslade uses a west-ward postcode proxy. Other Leighton Buzzard records remain comparison context.':market.core?'Core market. Nearby localities are listed separately as comparison areas.':'Comparison geography. This is a wider postal area, not the named core town.';
    $('sale-count').textContent=number(rows.length);
    const latest=rows.filter(r=>r[0].startsWith('2025')&&r[9]==='A');
    $('median').textContent=latest.length?money(quantile(latest.map(r=>r[1]),.5)):'Unavailable';
    $('median-caption').textContent='2025, '+number(latest.length)+' standard sales';
    $('history-years').textContent=rows.length?String(1+Number(rows[0][0].slice(0,4))-Math.min(...rows.map(r=>Number(r[0].slice(0,4))))):'0';
    $('count-caption').textContent=market.name;
    populateRoads();renderHistory();estimate();
  }catch(error){$('load-error').hidden=false;$('load-error').textContent=error.message;}
}

function populateRoads(){
  const choices=new Map();
  for(const r of rows){
    if(r[0]<'2010-01-01'||r[0]>'2025-12-31'||r[9]!=='A')continue;
    const pc=r[4].replace(/ /g,'').toUpperCase(),sector=pc.length>=5?pc.slice(0,-2):'unknown';
    if(r[3])choices.set(r[3]+'|'+sector,{street:r[3],sector});
  }
  $('road').innerHTML='<option value="">Area estimate, no road selected</option>'+[...choices.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([value,r])=>'<option value="'+esc(value)+'">'+esc(titleCase(r.street)+' · '+r.sector)+'</option>').join('');
}
function titleCase(s){return s.toLowerCase().replace(/(^|[\s-])\S/g,c=>c.toUpperCase())}
function filteredRows(){const q=$('sale-search').value.toUpperCase().replace(/\s/g,''),kind=$('history-type').value,start=$('from-year').value;return rows.filter(r=>(!kind||r[2]===kind)&&r[0]>=start+'-01-01'&&(!q||(r[3]+r[4]).toUpperCase().replace(/\s/g,'').includes(q)))}

function renderHistory(){
  const selected=filteredRows();renderChart(selected);
  const pages=Math.max(1,Math.ceil(selected.length/20));page=Math.min(page,pages-1);
  $('sales-body').innerHTML=selected.slice(page*20,page*20+20).map(r=>'<tr><td>'+esc(titleCase([r[6],r[5],r[3]].filter(Boolean).join(' ')))+(r[9]==='B'?' <span title="Additional transaction category">†</span>':'')+'</td><td>'+esc(r[4])+'</td><td>'+types[r[2]]+'</td><td>'+esc(r[0])+'</td><td class="numeric">'+money(r[1])+'</td></tr>').join('')||'<tr><td colspan="5">No matching recorded sales.</td></tr>';
  $('page-count').textContent=number(selected.length)+' sales · Page '+(page+1)+' of '+pages;
  $('prev').disabled=page===0;$('next').disabled=page>=pages-1;
}

function renderChart(selected){
  const groups=new Map();
  for(const r of selected){if(r[9]!=='A')continue;const year=r[0].slice(0,4);if(!groups.has(year))groups.set(year,[]);groups.get(year).push(r[1]);}
  const points=[...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([year,values])=>({year:Number(year),median:quantile(values,.5),low:quantile(values,.25),high:quantile(values,.75),n:values.length}));
  if(!points.length){$('trend').innerHTML='<p>No standard sale records for these filters.</p>';return;}
  const W=1080,H=285,L=70,R=20,T=15,B=40;
  const ymin=0,ymax=Math.ceil(Math.max(...points.map(p=>p.high))/100000)*100000||100000;
  const xmin=points[0].year,xmax=points[points.length-1].year;
  const x=year=>L+(year-xmin)/Math.max(1,xmax-xmin)*(W-L-R),y=v=>T+(1-v/ymax)*(H-T-B);
  const line=points.map((p,i)=>(i?'L':'M')+x(p.year).toFixed(2)+','+y(p.median).toFixed(2)).join(' ');
  const band=points.map((p,i)=>(i?'L':'M')+x(p.year)+','+y(p.high)).join(' ')+' '+[...points].reverse().map(p=>'L'+x(p.year)+','+y(p.low)).join(' ')+' Z';
  let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Annual nominal prices from '+xmin+' to '+xmax+'"><title>Annual median and middle half of standard completed sale prices</title>';
  for(let i=0;i<=4;i++){const v=ymax*i/4;svg+='<line x1="'+L+'" y1="'+y(v)+'" x2="'+(W-R)+'" y2="'+y(v)+'" stroke="#e4e8df"/><text x="'+(L-12)+'" y="'+(y(v)+4)+'" fill="#697770" text-anchor="end" font-size="11">£'+Math.round(v/1000)+'k</text>'}
  svg+='<path d="'+band+'" fill="#e0e6d5"/><path d="'+line+'" fill="none" stroke="#183d35" stroke-width="2.5"/>';
  for(const p of points){svg+='<circle cx="'+x(p.year)+'" cy="'+y(p.median)+'" r="3" fill="#183d35"><title>'+p.year+': '+money(p.median)+' · '+number(p.n)+' sales</title></circle>';if(p.year===xmin||p.year===xmax||p.year%5===0)svg+='<text x="'+x(p.year)+'" y="'+(H-10)+'" text-anchor="middle" fill="#697770" font-size="11">'+p.year+'</text>';}
  $('trend').innerHTML=svg+'</svg>';
}

function estimate(){
  if(!market)return;
  const model=research.model,kind=$('estimate-type').value,month=$('valuation-month').value;
  const area=research.hpi[market.hpi_area],index=area?.[kind]?.[month];
  const support=market.training_by_type[kind]||0,total=Object.values(market.training_by_type).reduce((a,b)=>a+b,0);
  $('ask-comparison').hidden=true;
  if(!index||support<30||total<100){
    $('estimate-price').textContent='Insufficient evidence';$('estimate-range').textContent=!index?'Choose a month with a published local index.':'Too few supported '+types[kind].toLowerCase()+' sales.';
    $('estimate-context').textContent=market.name==='Linslade'?'Linslade address coverage remains incomplete. Select Leighton Buzzard context for a clearly labelled broader comparison.':'No numerical estimate is released for this combination.';
    $('estimate-warning').textContent='No price is shown when the market, house type or valuation month lacks support. A broader comparison is not a substitute for a verified local valuation.';
    return;
  }
  const [street='',sector='unknown']=$('road').value.split('|');
  const values={market_type:market.name+'|'+kind,tenure:$('tenure').value,new_build:$('new-build').value,sector_type:market.name+'|'+sector+'|'+kind,road_type:market.name+'|'+street+'|'+sector+'|'+kind,period:month.slice(0,4)+'Q'+Math.ceil(Number(month.slice(5))/3)};
  let log=model.kind==='median'?(model.groups[values.market_type]??model.global):model.intercept;
  if(model.kind!=='median')for(const [f,weights] of Object.entries(model.weights))log+=weights[values[f]]||0;
  const centre=Math.exp(log)*index,q=model.log_interval_radius;
  $('estimate-price').textContent=money(Math.round(centre/1000)*1000);
  $('estimate-range').textContent=money(Math.round(centre*Math.exp(-q)/1000)*1000)+' to '+money(Math.round(centre*Math.exp(q)/1000)*1000)+' · nominal 80% range';
  const n=model.counts[values.road_type]||0;
  const roadApplied=!!model.weights?.road_type?.[values.road_type];
  $('estimate-context').textContent=market.name+' · '+types[kind]+' · '+month+'. '+number(support)+' training sales of this type. '+(roadApplied?'Road estimate draws on '+n+' sales, with shrinkage.':'No supported road effect applied. This is a broader area estimate.');
  const asking=Number($('asking').value);
  if(asking>0){const gap=asking/centre-1;$('ask-comparison').hidden=false;$('ask-comparison').textContent='Asking price is '+pct(Math.abs(gap))+' '+(gap>=0?'above':'below')+' the model median. This alone does not establish value.';}
  $('estimate-warning').textContent='This range reflects a model without bedrooms, floor area or condition. The '+month+' local HPI is the time input, from the release on '+research.hpi_release+'. Estimates for unseen periods are not forecasts.';
}

function renderEvidence(){
  const e=research.evaluation;
  $('test-error').textContent=pct(e.test.median_ape);$('mae').textContent=money(e.test.mae);$('coverage').textContent=pct(e.test.interval_coverage);$('test-n').textContent=number(e.test.n);
  $('model-design').textContent='Train on 2010 to 2023. Choose the model using early 2024 sales. Calibrate the range on late 2024. Test on 2025. Fifteen per cent of properties are reserved from training. The website model is then refitted through 2025.';
  $('model-caveat').textContent=e.caveat+' The overall interval coverage is not guaranteed for every town or individual house.';
  $('model-body').innerHTML=e.candidates.map(c=>'<tr class="'+(c.name===e.selected?'selected-model':'')+'"><td>'+esc(c.name)+(c.name===e.selected?'<span class="selected-label">SELECTED</span>':'')+'</td><td>'+money(c.selection.mae)+'</td><td>'+money(c.test.mae)+'</td><td>'+pct(c.test.median_ape)+'</td></tr>').join('');
  $('market-errors').innerHTML=Object.entries(e.by_market).map(([k,v])=>'<tr><td>'+esc(k)+'</td><td>'+number(v.n)+'</td><td>'+money(v.mae)+'</td><td>'+pct(v.median_ape)+'</td><td>'+pct(v.interval_coverage)+'</td></tr>').join('');
  $('hpi-note').textContent='Local authority and house-type indices through '+research.profile.latest_hpi_month+', released '+research.hpi_release+'. The observed index adjusts for time. This revised-data experiment does not establish forecasting accuracy before the index was available.';
  $('geography-note').textContent=research.geography_note;
}

async function init(){
  try{
    research=await getJSON('data/research.json');
    $('snapshot').textContent=number(research.profile.sales_count)+' official sales · '+research.generated;
    $('date-range').textContent=research.profile.first_date+' to '+research.profile.last_date;
    $('market').innerHTML='<optgroup label="Core markets">'+research.markets.filter(m=>m.core).map(m=>'<option>'+esc(m.name)+'</option>').join('')+'</optgroup><optgroup label="Wider comparison areas">'+research.markets.filter(m=>!m.core).map(m=>'<option>'+esc(m.name)+'</option>').join('')+'</optgroup>';
    $('market').disabled=false;$('market').value='Didcot';
    $('from-year').innerHTML=Array.from({length:32},(_,i)=>'<option>'+(1995+i)+'</option>').join('');$('from-year').value='1995';
    $('valuation-month').max=research.profile.latest_hpi_month;$('valuation-month').value=research.profile.latest_hpi_month;
    renderEvidence();await selectMarket();
    $('market').addEventListener('change',selectMarket);
    for(const id of ['history-type','from-year','sale-search'])$(id).addEventListener(id==='sale-search'?'input':'change',()=>{page=0;renderHistory()});
    $('prev').addEventListener('click',()=>{page--;renderHistory()});$('next').addEventListener('click',()=>{page++;renderHistory()});
    $('price-form').addEventListener('submit',event=>{event.preventDefault();estimate()});
    for(const id of ['estimate-type','valuation-month','road','tenure','new-build'])$(id).addEventListener('change',estimate);
    $('asking').addEventListener('input',estimate);
    window.houseWatchReady=true;
  }catch(error){$('load-error').hidden=false;$('load-error').textContent=error.message;$('snapshot').textContent='Research data unavailable';}
}
init();
