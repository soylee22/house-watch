"""Build from official PPD identities and allowlisted non-address EPC fields."""
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
    tables=['transactions','transaction_geography']
    if any((destination/'data').glob('attributes-*.json')):tables.append('official EPC non-address projection')
    (destination/'public-manifest.json').write_text(json.dumps({'files':manifest,'source_tables':tables,
                                                             'household_data_exported':False,'epc_address_fields_exported':False},indent=2))


def build(state,hpi,model_dir,destination,attributes_path=None):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    data=destination/'data';data.mkdir(exist_ok=True)
    records,model_rows,indices,excluded=load_sales(state,hpi)
    profile=json.loads((model_dir/'profile.json').read_text())
    evaluation=json.loads((model_dir/'evaluation.json').read_text())
    model=json.loads((model_dir/'model.json').read_text())
    attributes={};area_result={}
    if attributes_path:
        from property_attributes import property_id
        allowed=('certificate_id','inspection_date','available_date','area_m2','energy_rating','built_form','property_type','habitable_rooms','area_basis')
        for observation in json.loads(Path(attributes_path).read_text()):
            if observation.get('source')!='official EPC':raise ValueError('Public attribute source must be official EPC')
            attributes.setdefault(observation['property_id'],[]).append({k:observation.get(k) for k in allowed})
        area_result=json.loads((model_dir/'area-result.json').read_text())
    markets=[]
    # Nothing is exported from properties, feedback, messages, outbox or settings.
    for market in sorted({r['market'] for r in records}):
        rows=[r for r in records if r['market']==market]
        slug=market.lower().replace(' ','-')
        projected=[[r['date'],r['price'],r['type'],r['street'],r['postcode'],r['number'],r['unit'],r['new_build'],r['tenure'],r['category']] for r in rows]
        projected.sort(reverse=True)
        (data/(slug+'.json')).write_text(json.dumps(projected,separators=(',',':')))
        if attributes_path:
            # Keys come from PPD addresses, not the separately licensed EPC address fields.
            projection={}
            for row in rows:
                pid=property_id(row)
                if pid in attributes:
                    key='|'.join(str(row.get(k,'')).strip().upper() for k in ('postcode','number','unit','street'))
                    projection[key]=attributes[pid]
            (data/('attributes-'+slug+'.json')).write_text(json.dumps(projection,separators=(',',':')))
        training=[r for r in model_rows if r['market']==market and '2010-01-01'<=r['date']<'2026-01-01']
        markets.append({'name':market,'slug':slug,'n':len(rows),
                        'training_by_type':dict(Counter(r['type'] for r in training)),
                        'hpi_area':AREA[market.removesuffix(' surrounds')],
                        'core':market in ('Didcot','Fleet','Flitwick','Hitchin','Linslade')})
    hpi_json={}
    for (area,month,kind),value in indices.items():
        hpi_json.setdefault(area,{}).setdefault(kind,{})[month]=value
    payload={'profile':profile,'evaluation':evaluation,'model':model,'markets':markets,'hpi':hpi_json,
             'columns':['date','price','type','street','postcode','number','unit','new_build','tenure','category'],
             'generated':profile['source_snapshot'],'hpi_release':profile['hpi_release'],
             'geography_note':'Core markets and surrounding postal areas are separate. Linslade uses explicit locality labels plus 201 postcodes whose current centroids fall in Leighton-Linslade West ward (E05014416). This is a stated ward proxy, not an exact house boundary. Unresolved and other Leighton Buzzard postcodes remain broader comparison context.'}
    payload['area_model']=area_result.get('model',{'enabled':False})
    payload['area_evaluation']=area_result.get('evaluation')
    payload['attributes_available']=bool(attributes_path)
    if attributes_path:
        payload['attribute_coverage']=json.loads((model_dir/'area-coverage.json').read_text())
        payload['epc_note']='Official domestic EPC extract through October 2026, retrieved 11 November 2026. Raw EPC addresses and contact fields are excluded. Internal floor area and energy rating retain certificate dates. Habitable rooms are not bedrooms.'
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
