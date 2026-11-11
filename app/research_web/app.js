'use strict';
const $=id=>document.getElementById(id);
const money=n=>new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP',maximumFractionDigits:0}).format(n);
const number=n=>new Intl.NumberFormat('en-GB').format(n);
const pct=n=>(100*n).toFixed(1)+'%';
const types={D:'Detached',S:'Semi-detached',T:'Terraced'};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let research,market,rows=[],properties=[],page=0,requestVersion=0;
let attributes={},areaOrigin='';
const cache=new Map();
const attributeCache=new Map();
const quantile=(xs,p)=>{const a=[...xs].sort((x,y)=>x-y);if(!a.length)return 0;const at=(a.length-1)*p,i=Math.floor(at);return a[i]+(a[Math.min(i+1,a.length-1)]-a[i])*(at-i)};

async function getJSON(url){const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw Error('Could not load research data ('+response.status+').');return response.json()}

async function selectMarket(){
  const version=++requestVersion;
  market=research.markets.find(m=>m.name===$('market').value);
  $('predictor-market').value=market.name;
  $('sale-count').textContent='…';
  try{
    if(!cache.has(market.slug))cache.set(market.slug,await getJSON('data/'+market.slug+'.json'));
    if(research.attributes_available&&!attributeCache.has(market.slug))attributeCache.set(market.slug,await getJSON('data/attributes-'+market.slug+'.json'));
    if(version!==requestVersion)return;
    rows=cache.get(market.slug);page=0;
    attributes=attributeCache.get(market.slug)||{};
    $('market-description').textContent=market.name==='Linslade'?'Linslade uses a west-ward postcode proxy. Other Leighton Buzzard records remain comparison context.':market.core?'Core market. Nearby localities are listed separately as comparison areas.':'Comparison geography. This is a wider postal area, not the named core town.';
    $('sale-count').textContent=number(rows.length);
    const latest=rows.filter(r=>r[0].startsWith('2025')&&r[9]==='A');
    $('median').textContent=latest.length?money(quantile(latest.map(r=>r[1]),.5)):'Unavailable';
    $('median-caption').textContent='2025, '+number(latest.length)+' standard sales';
    $('history-years').textContent=rows.length?String(1+Number(rows[0][0].slice(0,4))-Math.min(...rows.map(r=>Number(r[0].slice(0,4))))):'0';
    $('count-caption').textContent=market.name;
    populateRoads();prepareProperties();renderHistory();estimate();
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
function prepareProperties(){
  const grouped=new Map();
  for(const r of rows){
    if(r[9]!=='A'||!r[4]||!r[5])continue;
    const key=[r[4],r[5],r[6],r[3]].map(s=>s.trim().toUpperCase()).join('|');
    if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(r);
  }
  properties=[...grouped.entries()].map(([key,history])=>({key,history:history.sort((a,b)=>b[0].localeCompare(a[0])),label:titleCase([history[0][6],history[0][5],history[0][3]].filter(Boolean).join(' '))+' · '+history[0][4]})).sort((a,b)=>a.label.localeCompare(b.label));
  $('property-search').value='';$('material-change').checked=false;$('road').disabled=false;filterProperties();
}
function filterProperties(){
  const normal=s=>s.toUpperCase().replace(/[^A-Z0-9]/g,''),q=normal($('property-search').value);
  const matches=q.length>=3?properties.map((p,i)=>({p,i})).filter(({p})=>normal(p.label).includes(q)):[];
  $('property').innerHTML='<option value="">Area or road estimate, no address selected</option>'+matches.slice(0,100).map(({p,i})=>'<option value="'+i+'">'+esc(p.label)+'</option>').join('');
  $('road').disabled=false;
  $('area-m2').value='';$('bedrooms').value='';areaOrigin='';showAreaEvidence(true);
  $('property-match-note').textContent=q.length<3?'Enter at least three characters of a postcode or address. Lookup stays in this browser.':matches.length?number(matches.length)+' recorded addresses. Select the exact house. '+(matches.length>100?'Narrow the search to see all matches.':''):'No recorded address matches. Check the area or use a broader road estimate.';
}
function chooseProperty(){
  $('road').disabled=$('property').value!=='';
  if($('property').value!==''){
    const p=properties[Number($('property').value)],r=p.history[0];
    $('estimate-type').value=r[2];$('tenure').value=r[8]==='L'?'L':'F';$('new-build').value='N';
    const sector=r[4].replace(/ /g,'').toUpperCase().slice(0,-2),road=r[3]+'|'+sector;
    if([...$('road').options].some(o=>o.value===road))$('road').value=road;else $('road').value='';
    $('material-change').checked=false;
  }
  showAreaEvidence(true);
  estimate();
}
function datedAttribute(){
  if($('property').value==='')return null;
  const property=properties[Number($('property').value)],month=$('valuation-month').value;
  if(!/^\d{4}-\d{2}$/.test(month))return null;
  const [y,m]=month.split('-').map(Number),cutoff=new Date(Date.UTC(y,m,0)).toISOString().slice(0,10);
  const history=(attributes[property.key]||[]).filter(r=>r.available_date<=cutoff&&r.inspection_date<=cutoff).sort((a,b)=>a.available_date.localeCompare(b.available_date)||a.inspection_date.localeCompare(b.inspection_date));
  const latest=history[history.length-1];if(!latest)return null;
  const peers=history.filter(r=>r.available_date===latest.available_date);
  if(new Set(peers.map(r=>[r.area_m2,r.habitable_rooms,r.built_form].join('|'))).size>1)return null;
  if((Date.parse(cutoff)-Date.parse(latest.inspection_date))/86400000>5*365.25)return null;
  const form=(latest.built_form||'').toLowerCase(),expected=form.includes('semi')?'S':form.includes('terrace')?'T':form==='detached'?'D':null;
  if(latest.property_type&&!['house','bungalow'].includes(latest.property_type.toLowerCase()))return null;
  if(expected&&expected!==$('estimate-type').value)return null;
  return latest;
}
function showAreaEvidence(fill=false){
  const observation=datedAttribute();
  if(fill||areaOrigin==='certificate'){
    $('area-m2').value=observation?observation.area_m2:'';areaOrigin=observation?'certificate':'';
  }
  if(areaOrigin==='user'){$('area-source-note').textContent='User-entered internal area. Check the measurement basis and whether it describes the selected valuation date.';return;}
  if(observation){
    const certificate=observation.certificate_id;
    $('area-source-note').innerHTML=esc(observation.area_m2+' m² · '+Math.round(observation.area_m2*10.7639)+' sq ft · EPC assessed '+observation.inspection_date+' · energy rating '+(observation.energy_rating||'unknown')+'. ')+(/^\d{4}(?:-\d{4}){4}$/.test(certificate)?'<a href="https://find-energy-certificate.service.gov.uk/energy-certificate/'+esc(certificate)+'" target="_blank" rel="noopener noreferrer">Check certificate ↗</a>':'');
  }else $('area-source-note').textContent='No unambiguous compatible EPC area, at most five years old, was available by this valuation month. Enter a known internal area or use the previous-sale method.';
}
function rowFeatures(r){
  const sector=r[4].replace(/ /g,'').toUpperCase().slice(0,-2);
  return {market_type:market.name+'|'+r[2],tenure:r[8],new_build:r[7],sector_type:market.name+'|'+sector+'|'+r[2],road_type:market.name+'|'+r[3]+'|'+sector+'|'+r[2],period:r[0].slice(0,4)+'Q'+Math.ceil(Number(r[0].slice(5,7))/3)};
}
function modelPrice(values,index){
  const model=research.model;
  let log=model.kind==='median'?(model.groups[values.market_type]??model.global):model.intercept;
  if(model.kind!=='median')for(const [f,weights] of Object.entries(model.weights))log+=weights[values[f]]||0;
  return Math.exp(log)*index;
}
function ageBand(years){return years<=5?'1 to 5 years':years<=10?'5 to 10 years':years<=20?'10 to 20 years':'Over 20 years'}
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
  $('address-breakdown').hidden=true;
  $('attribute-breakdown').hidden=true;$('estimate-method').textContent='ACHIEVED-PRICE ESTIMATE';
  if(!index||month<'2010-01'||month>research.profile.latest_hpi_month||support<30||total<100){
    $('estimate-price').textContent='Insufficient evidence';$('estimate-range').textContent=!index?'Choose a month with a published local index.':'Too few supported '+types[kind].toLowerCase()+' sales.';
    $('estimate-context').textContent=market.name==='Linslade'?'Linslade address coverage remains incomplete. Select Leighton Buzzard context for a clearly labelled broader comparison.':'No numerical estimate is released for this combination.';
    $('estimate-warning').textContent='No price is shown when the market, house type or valuation month lacks support. A broader comparison is not a substitute for a verified local valuation.';
    return;
  }
  const [street='',sector='unknown']=$('road').value.split('|');
  const values={market_type:market.name+'|'+kind,tenure:$('tenure').value,new_build:$('new-build').value,sector_type:market.name+'|'+sector+'|'+kind,road_type:market.name+'|'+street+'|'+sector+'|'+kind,period:month.slice(0,4)+'Q'+Math.ceil(Number(month.slice(5))/3)};
  const base=modelPrice(values,index);
  let centre=base,q=model.log_interval_radius,addressNote='';
  if($('property').value!==''){
    const property=properties[Number($('property').value)];
    const eligible=property.history.filter(r=>r[0].slice(0,7)<=month);
    const previous=eligible[0];
    const [yearPart,monthPart]=month.split('-').map(Number);
    const currentDate=new Date(Date.UTC(yearPart,monthPart,0)).toISOString().slice(0,10);
    const gapDays=previous?(Date.parse(currentDate)-Date.parse(previous[0]))/86400000:0;
    const years=gapDays/365.25;
    const previousIndex=previous?research.hpi[market.hpi_area]?.[previous[2]]?.[previous[0].slice(0,7)]:null;
    let reason='';
    if(!previous)reason='No sale of this exact address precedes the valuation date.';
    else if($('material-change').checked)reason='Physical alterations need an attribute model. The previous-sale adjustment is withheld.';
    else if(gapDays<(model.address_model?.minimum_gap_days||365))reason='The latest preceding sale is less than a year old. The address model is withheld for recent sales and flips.';
    else if(previous[2]!==kind||previous[8]!==$('tenure').value||$('new-build').value!=='N')reason='Recorded house type, tenure or build status differs. The earlier sale needs review.';
    else if(eligible.filter(r=>r[0]===previous[0]).some(r=>r[1]!==previous[1]))reason='Conflicting sale prices on the same day need review.';
    else if(!previousIndex)reason='A published local index is unavailable for the previous sale month.';
    else if(!model.address_model?.enabled)reason='The prior-sale model has insufficient validation support.';
    if(!reason){
      const band=ageBand(years),weight=model.address_model.weights[band].weight;
      const priorBase=modelPrice(rowFeatures(previous),previousIndex);
      const anchored=previous[1]*base/priorBase;
      centre=Math.exp((1-weight)*Math.log(base)+weight*Math.log(anchored));
      q=model.address_model.intervals[band].log_radius;
      const marketOnly=previous[1]*index/previousIndex;
      $('address-breakdown').hidden=false;
      $('address-breakdown').innerHTML='<strong>'+esc(property.label)+'</strong><dl><div><dt>Previous achieved sale</dt><dd>'+money(previous[1])+' · '+esc(previous[0])+'</dd></div><div><dt>Local type-specific market movement</dt><dd>'+((index/previousIndex-1)>=0?'+':'')+pct(index/previousIndex-1)+'</dd></div><div><dt>Previous sale, indexed to '+esc(month)+'</dt><dd>'+money(marketOnly)+'</dd></div><div><dt>Prior sale with recorded-factor adjustment</dt><dd>'+money(anchored)+'</dd></div><div><dt>Independent area/road estimate</dt><dd>'+money(base)+'</dd></div><div><dt>Weight on this house’s previous-sale evidence</dt><dd>'+pct(weight)+'</dd></div></dl><p>The blend weight is selected from earlier repeated sales. Bedrooms, extensions and condition changes are not separately priced.</p>';
      addressNote='Exact address matched. Previous sale '+previous[0]+'. The estimate combines that house’s sale evidence with the area/road model. ';
    }else addressNote='Address adjustment not applied: '+reason+' Showing the broader area/road estimate. ';
  }
  $('estimate-price').textContent=money(Math.round(centre/1000)*1000);
  $('estimate-range').textContent=money(Math.round(centre*Math.exp(-q)/1000)*1000)+' to '+money(Math.round(centre*Math.exp(q)/1000)*1000)+' · nominal 80% range';
  const n=model.counts[values.road_type]||0;
  const roadApplied=!!model.weights?.road_type?.[values.road_type];
  $('estimate-context').textContent=addressNote+market.name+' · '+types[kind]+' · '+month+'. '+number(support)+' training sales of this type. '+(roadApplied?'Road estimate draws on '+n+' sales, with shrinkage.':!addressNote?'No supported road effect applied. This is a broader area estimate.':'');
  const asking=Number($('asking').value);
  if(asking>0){const gap=asking/centre-1;$('ask-comparison').hidden=false;$('ask-comparison').textContent='Asking price is '+pct(Math.abs(gap))+' '+(gap>=0?'above':'below')+' the model median. This alone does not establish value.';}
  $('estimate-warning').textContent='This range reflects a model without bedrooms, floor area or condition. The '+month+' local HPI is the time input, from the release on '+research.hpi_release+'. Estimates for unseen periods are not forecasts.';
  if(!$('address-breakdown').hidden){
    const local=research.evaluation.address_model?.by_market?.[market.name];
    if(local?.n>=30)$('estimate-warning').textContent+=' In '+market.name+', the address model’s nominal 80% ranges covered '+pct(local.interval_coverage)+' of '+number(local.n)+' historical test sales.';
  }
  const areaValue=Number($('area-m2').value),method=$('valuation-method').value,areaModel=research.area_model;
  const wantsArea=method==='area'||(method==='auto'&&$('area-m2').value!=='');
  if(method==='previous'&&areaValue>0)$('estimate-context').textContent+=' The selected previous-sale method does not use the floor-area input.';
  if(wantsArea){
    const areaSupport=areaModel?.training_by_market_type?.[values.market_type]||0;
    if(!areaModel?.enabled||!Number.isFinite(areaValue)||areaValue<areaModel.area_min_m2||areaValue>areaModel.area_max_m2||areaSupport<30){
      $('estimate-price').textContent='Size estimate unavailable';$('estimate-range').textContent=areaModel?.enabled?'Use '+Math.ceil(areaModel.area_min_m2)+' to '+Math.floor(areaModel.area_max_m2)+' m² with at least 30 matched local/type training sales.':'No validated floor-area model is available.';
      $('estimate-context').textContent='Enter supported internal floor area, or choose the previous-sale / area method.';
      $('estimate-warning').textContent='No numerical size adjustment is made outside the fitted support.';$('ask-comparison').hidden=true;$('address-breakdown').hidden=true;return;
    }
    let log=areaModel.intercept;
    for(const [feature,weights] of Object.entries(areaModel.weights))log+=weights[values[feature]]||0;
    log+=areaModel.log_area_coefficient*Math.log(areaValue/areaModel.reference_area_m2);
    const sizePrice=Math.exp(log)*index,sizeRadius=areaModel.log_interval_radius;
    $('estimate-method').textContent='FLOOR-AREA MODEL · ACHIEVED PRICE';
    $('estimate-price').textContent=money(Math.round(sizePrice/1000)*1000);
    $('estimate-range').textContent=money(Math.round(sizePrice*Math.exp(-sizeRadius)/1000)*1000)+' to '+money(Math.round(sizePrice*Math.exp(sizeRadius)/1000)*1000)+' · nominal 80% range';
    $('estimate-context').textContent=market.name+' · '+types[kind]+' · '+month+' · '+areaValue+' m². '+number(areaSupport)+' dated local/type training sales. Floor area changes this estimate. The previous-sale method is a separate comparison.';
    $('attribute-breakdown').hidden=false;
    $('attribute-breakdown').innerHTML='<strong>Physical evidence used</strong><dl><div><dt>Internal floor area</dt><dd>'+esc(areaValue)+' m² · '+number(Math.round(areaValue*10.7639))+' sq ft</dd></div><div><dt>Measurement source</dt><dd>'+esc(areaOrigin==='certificate'?'Dated official EPC':'User-entered, not verified')+'</dd></div><div><dt>Bedrooms</dt><dd>'+esc($('bedrooms').value||'Unknown')+' · no fitted bedroom adjustment</dd></div><div><dt>Previous-sale / area method</dt><dd>'+money(Math.round(centre/1000)*1000)+' · separate estimate</dd></div></dl><p>Floor area already captures much of the difference between larger and smaller houses. An extra bedroom is not given an invented cash premium. EPC area may differ from an agent’s floor-plan total.</p>';
    if(!$('address-breakdown').hidden)$('address-breakdown').innerHTML='<p><strong>Previous-sale method, for comparison</strong></p>'+$('address-breakdown').innerHTML;
    const local=research.area_evaluation?.by_market?.[market.name];
    $('estimate-warning').textContent='This model adjusts for floor area. It does not separately price bedrooms, condition, parking or an extension’s quality. The '+month+' HPI comes from the release on '+research.hpi_release+'. '+(areaOrigin==='user'?'The measurement is entered by you. ':'')+(local?.n>=30?'In '+market.name+', nominal 80% size-model ranges covered '+pct(local.interval_coverage)+' of '+number(local.n)+' test sales.':'');
    if(asking>0){const gap=asking/sizePrice-1;$('ask-comparison').hidden=false;$('ask-comparison').textContent='Asking price is '+pct(Math.abs(gap))+' '+(gap>=0?'above':'below')+' the size-model median. This alone does not establish value.';}
  }
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
  const address=e.address_model;
  if(address?.enabled){$('address-evidence').hidden=false;$('address-evidence').textContent='Exact-address test: '+number(address.test.n)+' later sales with a supported earlier sale. Median absolute percentage error '+pct(address.test.median_ape)+', MAE '+money(address.test.mae)+'. The area/road model on these same houses had MAE '+money(address.base_on_same_sales.mae)+'. Age-specific nominal 80% ranges covered '+pct(address.age_interval_coverage)+'. This is a revised-data conditional test. Physical alterations remain unmeasured.';}
  const area=research.area_evaluation;
  if(area?.enabled){$('area-evidence').hidden=false;$('area-evidence').textContent='Floor-area test: '+number(area.test.n)+' later sales with a dated EPC. Median error '+pct(area.test.median_ape)+', MAE '+money(area.test.mae)+'. The original area/road model on these same sales had median error '+pct(area.base_on_same_sales.median_ape)+' and MAE '+money(area.base_on_same_sales.mae)+'. Nominal 80% ranges covered '+pct(area.test.interval_coverage)+'. Certificates were available by each sale date. Bedrooms are not separately modelled.';}
  $('epc-note').textContent=research.epc_note||'Dated physical-attribute evidence is not available in this snapshot.';
}

async function init(){
  try{
    research=await getJSON('data/research.json');
    $('snapshot').textContent=number(research.profile.sales_count)+' official sales · '+research.generated;
    $('date-range').textContent=research.profile.first_date+' to '+research.profile.last_date;
    $('market').innerHTML='<optgroup label="Core markets">'+research.markets.filter(m=>m.core).map(m=>'<option>'+esc(m.name)+'</option>').join('')+'</optgroup><optgroup label="Wider comparison areas">'+research.markets.filter(m=>!m.core).map(m=>'<option>'+esc(m.name)+'</option>').join('')+'</optgroup>';
    $('market').disabled=false;$('market').value='Didcot';
    $('predictor-market').innerHTML=$('market').innerHTML;$('predictor-market').disabled=false;$('predictor-market').value='Didcot';
    $('from-year').innerHTML=Array.from({length:32},(_,i)=>'<option>'+(1995+i)+'</option>').join('');$('from-year').value='1995';
    $('valuation-month').max=research.profile.latest_hpi_month;$('valuation-month').value=research.profile.latest_hpi_month;
    renderEvidence();await selectMarket();
    $('market').addEventListener('change',selectMarket);
    $('predictor-market').addEventListener('change',event=>{$('market').value=event.target.value;selectMarket()});
    for(const id of ['history-type','from-year','sale-search'])$(id).addEventListener(id==='sale-search'?'input':'change',()=>{page=0;renderHistory()});
    $('prev').addEventListener('click',()=>{page--;renderHistory()});$('next').addEventListener('click',()=>{page++;renderHistory()});
    $('price-form').addEventListener('submit',event=>{event.preventDefault();estimate()});
    for(const id of ['estimate-type','valuation-month','road','tenure','new-build'])$(id).addEventListener('change',()=>{showAreaEvidence();estimate()});
    $('area-m2').addEventListener('input',()=>{areaOrigin='user';showAreaEvidence();estimate()});
    $('bedrooms').addEventListener('input',estimate);$('valuation-method').addEventListener('change',estimate);
    $('asking').addEventListener('input',estimate);
    $('property-search').addEventListener('input',()=>{filterProperties();estimate()});
    $('property').addEventListener('change',chooseProperty);
    $('material-change').addEventListener('change',estimate);
    window.houseWatchReady=true;
    if(location.hash)document.getElementById(location.hash.slice(1))?.scrollIntoView({block:'start'});
  }catch(error){$('load-error').hidden=false;$('load-error').textContent=error.message;$('snapshot').textContent='Research data unavailable';}
}
init();
