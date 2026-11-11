"""Reproducible reduced-feature price research, evaluated on later sales.

HPI is an explicit time offset. Optional quarter effects explain residual time
variation. Unseen quarters use the HPI path with zero residual quarter effect.
This is revised-snapshot research, not a vintage-correct forecasting backtest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder

from core import connect, import_sales

TYPE_NAMES={'D':'Detached','S':'Semi_Detached','T':'Terraced'}
AREA={'Didcot':'South Oxfordshire','Fleet':'Hart','Hitchin':'North Hertfordshire',
      'Flitwick':'Central Bedfordshire','Linslade':'Central Bedfordshire',
      'Leighton Buzzard context':'Central Bedfordshire'}
BASE_FEATURES=['market_type','tenure','new_build']
SCALES={'market_type':3.0,'tenure':1.0,'new_build':1.0,'sector_type':0.8,'road_type':0.35,'period':0.8}


def address_id(row):
    key='|'.join(str(row.get(k,'')).strip().upper() for k in ('postcode','number','unit','street'))
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def enrich(row):
    r=dict(row)
    r['market_type']=r['market']+'|'+r['type']
    pc=(r.get('postcode') or '').replace(' ','').upper()
    r['sector']=pc[:-2] if len(pc)>=5 else 'unknown'
    r['sector_type']=r['market']+'|'+r['sector']+'|'+r['type']
    r['road_type']=r['market']+'|'+r['street'].upper()+'|'+r['sector']+'|'+r['type']
    r['period']=r['date'][:4]+'Q'+str((int(r['date'][5:7])-1)//3+1)
    r['property_id']=address_id(r)
    return r


def load_sales(state,hpi_path):
    with connect(state) as db:
        records=[dict(r) for r in db.execute('SELECT t.*,g.locality,g.market,g.evidence FROM transactions t JOIN transaction_geography g ON t.id=g.transaction_id')]
    hpi=pd.read_csv(hpi_path).fillna('')
    indices={}
    for area in set(AREA.values()):
        subset=hpi[hpi.Region_Name==area]
        if subset.empty:raise ValueError('Missing HPI area '+area)
        for row in subset.to_dict('records'):
            for kind,prefix in TYPE_NAMES.items():
                value=row.get(prefix+'_Index')
                if value!='' and float(value)>0:indices[(area,row['Date'][:7],kind)]=float(value)
    rows=[];excluded=Counter()
    for row in records:
        if row['category']!='A':excluded['additional category B']+=1;continue
        if row['price']<=0:excluded['nonpositive price']+=1;continue
        r=enrich(row)
        core=r['market'].removesuffix(' surrounds')
        area=AREA.get(core)
        if area is None:raise ValueError('Unknown index area for '+r['market'])
        index=indices.get((area,r['date'][:7],r['type']))
        if index is None:excluded['no published type/area/month HPI']+=1;continue
        r['hpi_area']=area;r['hpi']=index;rows.append(r)
    return records,rows,indices,dict(excluded)


def fit(rows,features):
    y=np.array([math.log(r['price']/r['hpi']) for r in rows])
    if not features:
        groups={}
        for r,v in zip(rows,y):groups.setdefault(r['market_type'],[]).append(v)
        return {'kind':'median','groups':{k:float(np.median(v)) for k,v in groups.items()},'global':float(np.median(y))}
    enc=OneHotEncoder(handle_unknown='ignore',sparse_output=True)
    x=enc.fit_transform([[r[f] for f in features] for r in rows])
    scale=np.concatenate([np.full(len(c),SCALES[f]) for f,c in zip(features,enc.categories_)])
    model=Ridge(alpha=10.0,solver='lsqr',tol=1e-8).fit(x.multiply(scale).tocsr(),y)
    weights={};start=0
    for f,cats in zip(features,enc.categories_):
        weights[f]={str(c):float(model.coef_[start+j]*SCALES[f]) for j,c in enumerate(cats)}
        start+=len(cats)
    return {'kind':'ridge','intercept':float(model.intercept_),'weights':weights,'alpha':10.0,'feature_scales':{f:SCALES[f] for f in features}}


def predict(model,row):
    if row.get('hpi',0)<=0:raise ValueError('A supported dated HPI value is required')
    if model['kind']=='median':
        value=model['groups'].get(row['market_type'],model['global'])
    else:
        value=model['intercept']+sum(weights.get(row[f],0.0) for f,weights in model['weights'].items())
    return math.exp(value)*row['hpi']


def metrics(rows,predictions,q=None):
    if not rows:return {'n':0}
    actual=np.array([r['price'] for r in rows]);pred=np.array(predictions)
    result={'n':len(rows),'mae':float(np.mean(np.abs(pred-actual))),
            'median_ape':float(np.median(np.abs(pred/actual-1))),
            'bias':float(np.mean(pred-actual))}
    if q is not None:
        result['interval_coverage']=float(np.mean((actual>=pred*np.exp(-q))&(actual<=pred*np.exp(q))))
        result['median_interval_width']=float(np.median(pred*(math.exp(q)-math.exp(-q))))
    return result


def evaluate(rows):
    # Deterministically reserve 15% of properties from every training period.
    unseen=lambda r:int(r['property_id'][:8],16)%100<15
    train=[r for r in rows if '2010-01-01'<=r['date']<'2024-01-01' and not unseen(r)]
    selection=[r for r in rows if '2024-01-01'<=r['date']<'2024-07-01']
    calibration=[r for r in rows if '2024-07-01'<=r['date']<'2025-01-01']
    test=[r for r in rows if '2025-01-01'<=r['date']<'2026-01-01']
    if min(map(len,(train,selection,calibration,test)))<100:
        raise ValueError('Insufficient support for declared time folds')
    specs={'Indexed market/type median':[],
           'Place and house characteristics':BASE_FEATURES,
           'Place, postcode sector and road':BASE_FEATURES+['sector_type','road_type'],
           'Place, road and residual quarter effects':BASE_FEATURES+['sector_type','road_type','period']}
    candidates=[];fits={}
    for name,features in specs.items():
        model=fit(train,features);fits[name]=model
        candidates.append({'name':name,'features':features,
                           'selection':metrics(selection,[predict(model,r) for r in selection])})
    chosen=min(candidates,key=lambda c:c['selection']['mae']);model=fits[chosen['name']]
    residuals=sorted(abs(math.log(r['price']/predict(model,r))) for r in calibration)
    q=residuals[min(len(residuals)-1,math.ceil((len(residuals)+1)*0.8)-1)]
    for c in candidates:
        c['test']=metrics(test,[predict(fits[c['name']],r) for r in test],q if c is chosen else None)
    pred=[predict(model,r) for r in test]
    by_market={k:metrics([r for r in test if r['market']==k],
                         [p for r,p in zip(test,pred) if r['market']==k],q) for k in sorted({r['market'] for r in test})}
    by_type={k:metrics([r for r in test if r['type']==k],
                       [p for r,p in zip(test,pred) if r['type']==k],q) for k in TYPE_NAMES}
    new=[(r,p) for r,p in zip(test,pred) if unseen(r)]
    from address_model import evaluate_address_model
    address_config,address_evaluation=evaluate_address_model(model,rows)
    address_heldout=address_evaluation.pop('_heldout',{}) if address_evaluation else {}
    # Freeze evaluation before production refit. Final test is never used to select.
    final=fit([r for r in rows if '2010-01-01'<=r['date']<'2026-01-01'],chosen['features'])
    final['log_interval_radius']=q
    final['features']=chosen['features']
    final['name']=chosen['name']
    final['training_end']='2025-12-31'
    final['counts']=dict(Counter(r['road_type'] for r in rows if '2010-01-01'<=r['date']<'2026-01-01'))
    final['address_model']=address_config
    evaluation={'selected':chosen['name'],'candidates':candidates,'by_market':by_market,'by_type':by_type,
                'unseen_properties':metrics([r for r,p in new],[p for r,p in new],q),
                'test':metrics(test,pred,q),'fold_counts':{'train':len(train),'selection':len(selection),'calibration':len(calibration),'test':len(test)},
                'interval_target':0.8,'log_interval_radius':q,
                'design':'Train 2010–2023 excluding 15% of properties. Select on Jan–Jun 2024. Calibrate on Jul–Dec 2024. Test on 2025. Refit through 2025 for website.',
                'caveat':'Retrospective revised-data assessment. Type/area HPI for the target month is an observed market input. This does not test a real-time forecast before that index was published.',
                'missing_features':['bedrooms','floor area','bathrooms','condition','parking'],
                'bargain_flags':False}
    evaluation['address_model']=address_evaluation
    heldout=[{'id':r['id'],'date':r['date'],'market':r['market'],'type':r['type'],'actual':r['price'],'predicted':round(p,2),'unseen_property':unseen(r)} for r,p in zip(test,pred)]
    for row in heldout:row.update(address_heldout.get(row['id'],{}))
    return final,evaluation,heldout


def build(state,sources,hpi_path,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with connect(state) as db:
        if any(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('properties','feedback','messages','outbox')):
            raise ValueError('Use isolated public research state, not the household database')
        # Sources are complete current snapshots, so deleted upstream rows disappear.
        db.execute('DELETE FROM transaction_geography')
        db.execute('DELETE FROM transactions')
        for path in sources:import_sales(db,[path])
    all_records,rows,indices,excluded=load_sales(state,hpi_path)
    model,evaluation,heldout=evaluate(rows)
    (output/'model.json').write_text(json.dumps(model,separators=(',',':')))
    (output/'evaluation.json').write_text(json.dumps(evaluation,indent=2))
    (output/'heldout-predictions.json').write_text(json.dumps(heldout,separators=(',',':')))
    hpi_manifest=json.loads((Path(hpi_path).parent/'manifest.json').read_text())
    source_metadata=[json.loads(p.with_suffix('.json').read_text()) for p in sources if p.with_suffix('.json').exists()]
    profile={'sales_count':len(all_records),'model_supported_rows':len(rows),'excluded_from_model':excluded,
             'first_date':min(r['date'] for r in all_records),'last_date':max(r['date'] for r in all_records),
             'by_market':dict(Counter(r['market'] for r in all_records)),
             'latest_hpi_month':max(k[1] for k in indices),
             'source_snapshot':max((m['retrieved'][:10] for m in source_metadata),default='unknown'),
             'hpi_release':hpi_manifest['release_date'],
             'source_vintage':'Current linked-data snapshot, with a separately dated HPI release'}
    (output/'profile.json').write_text(json.dumps(profile,indent=2))
    print(json.dumps({'profile':profile,'selected':evaluation['selected'],'test':evaluation['test']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--hpi',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('sources',nargs='+',type=Path)
    a=p.parse_args();build(a.state,a.sources,a.hpi,a.output)
