const $=id=>document.getElementById(id);
const norm=s=>String(s||'').toLowerCase().replace(/[^a-z0-9 ]/g,' ').replace(/\s+/g,' ').trim();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const usd=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n);
const range=(l,h)=>l==null?'Not published':l===h||h==null?usd(l):`${usd(l)} - ${usd(h)}`;
const aliases={nyc:'new york',ny:'new york',sf:'san francisco',la:'los angeles',uhc:'unitedhealthcare',bcbs:'bcbs'};
const extras={'80053':'blood work blood test cmp metabolic','80048':'blood work blood test bmp metabolic','85025':'blood work blood test cbc blood count','80061':'blood work cholesterol lipid','84443':'blood work thyroid tsh','83036':'blood work diabetes a1c','72148':'back spine mri','73721':'knee mri','73221':'shoulder mri','70551':'brain head mri','90834':'therapy mental health'};
let data,filtered=[],limit=50;
function options(id,values){for(const v of [...new Set(values.filter(Boolean))].sort()){const o=document.createElement('option');o.value=v;o.textContent=v;$(id).append(o)}}
function price(r){const p=$('payer').value;return p?(r.payers?.[p]||{}):{low:r.cash_min,high:r.cash_max}}
function render(infer=false){
 let q=norm($('q').value).split(' ').map(w=>aliases[w]||w).join(' '), remaining=q;
 const cities=[...new Set(data.providers.map(p=>p.city).filter(Boolean))].sort((a,b)=>b.length-a.length);
 const requestedCity=['New York','Austin','Chicago','Los Angeles','Boston','Seattle','San Francisco','Houston','Dallas','Miami','Minneapolis','Charlotte','Scranton'].find(c=>new RegExp(`\\b${norm(c)}\\b`).test(q));
 const inferredCity=cities.find(c=>new RegExp(`\\b${norm(c)}\\b`).test(q));
 const payerNames=[...new Set(data.rows.flatMap(r=>Object.keys(r.payers||{})))].sort((a,b)=>b.length-a.length);
 const inferredPayer=payerNames.find(p=>{const name=norm(p);return name.length>=4 && (' '+q+' ').includes(' '+name+' ')});
 if(inferredCity){if(infer)$('city').value=inferredCity;remaining=remaining.replace(norm(inferredCity),'')}
 if(inferredPayer){if(infer)$('payer').value=inferredPayer;remaining=remaining.replace(norm(inferredPayer),'')}
 const words=remaining.trim().split(' ').filter(w=>w&&!['in','near','cost','price','prices','for','of'].includes(w));
 filtered=data.rows.filter(r=>{
  const p=data.providers[r.provider],t=data.procedures[r.code],v=price(r);
  if($('city').value&&p.city!==$('city').value)return false;
  if($('provider').value&&p.display_name!==$('provider').value)return false;
  if($('category').value&&t.category!==$('category').value)return false;
  if(v.low==null)return false;
  const hay=norm([t.label,r.code,extras[r.code]||'',p.display_name,p.city,p.state].join(' '));
  return words.every(w=>hay.includes(w));
 }).sort((a,b)=>price(a).low-price(b).low);
 $('interpretation').textContent=[requestedCity&&!inferredCity?`No verified source coverage for ${requestedCity} yet`:$('city').value&&`City: ${$('city').value}`,$('payer').value&&`Insurer: ${$('payer').value}`].filter(Boolean).join(' · ');
 $('count').textContent=`${filtered.length.toLocaleString()} matching published rates`;
 $('results').innerHTML=filtered.slice(0,limit).map(r=>{const p=data.providers[r.provider],t=data.procedures[r.code],v=price(r);return `<article class="result"><h3>${esc(t.label)}</h3><div class="muted">CPT ${r.code} · ${esc(p.display_name)} · ${esc([p.city,p.state].filter(Boolean).join(', ')||'Location not resolved')}</div><div class="price">${range(v.low,v.high)}</div><div class="muted">${esc($('payer').value||'Published cash rate')}${$('payer').value?' · Not your out-of-pocket estimate':''}</div><details><summary>Source, dates & billing details</summary><p>${esc(r.desc)}</p><p>Hospital source updated: ${esc(p.last_updated_on||'Not specified')} · Extracted: ${esc(p.extracted_at?.slice(0,10))}</p><p>Address in source: ${esc(p.hospital_address||'Not specified')}</p><p><a href="${esc(p.mrf_url)}" target="_blank" rel="noopener">Original hospital price file</a> · <a href="${esc(p.source_page_url||p.mrf_url)}" target="_blank" rel="noopener">Provider pricing page</a></p><p>Range may span settings, billing classes, modifiers and plans. These are published charges for a code, not an all-in treatment bundle. Ask the provider for a written estimate.</p></details></article>`}).join('')||'<div class="card"><h2 style="margin:0">No verified price matches yet.</h2><p>Try a broader search or another city. Missing data does not mean the service is unavailable. Our primary-source coverage is still growing; we do not substitute national averages for local prices.</p></div>';
 $('more').hidden=filtered.length<=limit;
 const u=new URL(location.href);u.searchParams.set('q',$('q').value);history.replaceState(null,'',u);
}
$('search').addEventListener('submit',e=>{e.preventDefault();for(const id of ['city','payer'])$(id).value='';limit=50;render(true)});
for(const id of ['city','provider','category','payer'])$(id).addEventListener('change',()=>{limit=50;render()});
$('more').addEventListener('click',()=>{limit+=50;render()});
$('download').addEventListener('click',()=>{const cells=[['code','treatment','provider','city','state','payer','low','high','source_updated','extracted','source_url'],...filtered.map(r=>{const p=data.providers[r.provider],v=price(r);return[r.code,data.procedures[r.code].label,p.display_name,p.city,p.state,$('payer').value||'cash',v.low,v.high,p.last_updated_on,p.extracted_at,p.mrf_url]})];const text=cells.map(row=>row.map(c=>'"'+String(c??'').replace(/"/g,'""')+'"').join(',')).join('\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/csv'}));a.download='costofcare-prices.csv';a.click();URL.revokeObjectURL(a.href)});
fetch('/data/dataset.json').then(r=>{if(!r.ok)throw Error();return r.json()}).then(async d=>{if(d.row_shards){d.rows=(await Promise.all(d.row_shards.map(u=>fetch(u).then(r=>{if(!r.ok)throw Error('Shard failed');return r.json()})))).flat()}data=d;options('city',d.providers.map(p=>p.city));options('provider',d.providers.map(p=>p.display_name));options('category',Object.values(d.procedures).map(t=>t.category));options('payer',d.rows.flatMap(r=>Object.keys(r.payers||{})));$('q').value=new URLSearchParams(location.search).get('q')||'';render(true)}).catch(()=>{$('count').textContent='The dataset could not load. Please try again.'});
