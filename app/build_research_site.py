"""Build a public website from an allowlisted projection of official sales only."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from price_model import AREA, TYPE_NAMES, load_sales


def write_manifest(destination):
    destination=Path(destination)
    manifest={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in destination.rglob('*') if p.is_file() and p.name!='public-manifest.json'}
    (destination/'public-manifest.json').write_text(json.dumps({'files':manifest,'source_tables':['transactions','transaction_geography'],
                                                             'household_data_exported':False},indent=2))


def build(state,hpi,model_dir,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    data=destination/'data';data.mkdir(exist_ok=True)
    records,model_rows,indices,excluded=load_sales(state,hpi)
    profile=json.loads((model_dir/'profile.json').read_text())
    evaluation=json.loads((model_dir/'evaluation.json').read_text())
    model=json.loads((model_dir/'model.json').read_text())
    markets=[]
    # Nothing is exported from properties, feedback, messages, outbox or settings.
    for market in sorted({r['market'] for r in records}):
        rows=[r for r in records if r['market']==market]
        slug=market.lower().replace(' ','-')
        projected=[[r['date'],r['price'],r['type'],r['street'],r['postcode'],r['number'],r['unit'],r['new_build'],r['tenure'],r['category']] for r in rows]
        projected.sort(reverse=True)
        (data/(slug+'.json')).write_text(json.dumps(projected,separators=(',',':')))
        training=[r for r in model_rows if r['market']==market and '2010-01-01'<=r['date']<'2026-01-01']
        markets.append({'name':market,'slug':slug,'n':len(rows),
                        'training_by_type':dict(Counter(r['type'] for r in training)),
                        'hpi_area':AREA[market.removesuffix(' surrounds')],
                        'core':market in ('Didcot','Fleet','Flitwick','Hitchin','Linslade')})
    hpi_json={}
    for (area,month,kind),value in indices.items():
        if month>='2010-01':hpi_json.setdefault(area,{}).setdefault(kind,{})[month]=value
    payload={'profile':profile,'evaluation':evaluation,'model':model,'markets':markets,'hpi':hpi_json,
             'columns':['date','price','type','street','postcode','number','unit','new_build','tenure','category'],
             'generated':profile['source_snapshot'],'hpi_release':profile['hpi_release'],
             'geography_note':'Core markets and surrounding postal areas are separate. Linslade uses explicit locality labels plus 201 postcodes whose current centroids fall in Leighton-Linslade West ward (E05014416). This is a stated ward proxy, not an exact house boundary. Unresolved and other Leighton Buzzard postcodes remain broader comparison context.'}
    (data/'research.json').write_text(json.dumps(payload,separators=(',',':')))
    base=Path(__file__).parent/'research_web'
    for name in ('index.html','style.css','app.js'):
        (destination/name).write_bytes((base/name).read_bytes())
    (destination/'.nojekyll').touch()
    write_manifest(destination)
    return payload


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--hpi',type=Path,required=True);p.add_argument('--models',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();payload=build(a.state,a.hpi,a.models,a.out)
    print(json.dumps({'public_sales':payload['profile']['sales_count'],'markets':len(payload['markets']),'household_data_exported':False}))
