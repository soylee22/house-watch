"""Floor-area hedonic model on strictly dated matched achieved sales.

The numeric feature is log(EPC internal m² / 100). Bedroom counts are not
available in EPCs. This model does not estimate a separate bedroom premium.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix,hstack
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder

from price_model import BASE_FEATURES,SCALES,fit as fit_base,metrics,predict as predict_base
from property_attributes import AttributeHistory,join_sales

FEATURES=BASE_FEATURES+['sector_type','road_type']


def fit(rows,with_area=True):
    encoder=OneHotEncoder(handle_unknown='ignore',sparse_output=True)
    x=encoder.fit_transform([[r[f] for f in FEATURES] for r in rows])
    scale=np.concatenate([np.full(len(c),SCALES[f]) for f,c in zip(FEATURES,encoder.categories_)])
    x=x.multiply(scale).tocsr()
    if with_area:
        x=hstack([x,csr_matrix(np.array([[math.log(r['area_m2']/100)] for r in rows]))],format='csr')
    target=np.array([math.log(r['price']/r['hpi']) for r in rows])
    ridge=Ridge(alpha=10,solver='lsqr',tol=1e-8).fit(x,target)
    weights={};start=0
    for feature,categories in zip(FEATURES,encoder.categories_):
        weights[feature]={str(c):float(ridge.coef_[start+i]*SCALES[feature]) for i,c in enumerate(categories)}
        start+=len(categories)
    return {'kind':'area-ridge','intercept':float(ridge.intercept_),'weights':weights,
            'log_area_coefficient':float(ridge.coef_[-1]) if with_area else 0,
            'reference_area_m2':100,'features':FEATURES,'alpha':10,
            'area_min_m2':float(np.quantile([r['area_m2'] for r in rows],.01)),
            'area_max_m2':float(np.quantile([r['area_m2'] for r in rows],.99))}


def predict(model,row):
    log=model['intercept']+sum(weights.get(row[f],0) for f,weights in model['weights'].items())
    log+=model['log_area_coefficient']*math.log(row['area_m2']/100)
    return math.exp(log)*row['hpi']


def evaluate(sales,observations):
    matched,coverage=join_sales(sales,observations)
    unseen=lambda r:int(r['property_id'][:8],16)%100<15
    train=[r for r in matched if '2010-01-01'<=r['date']<'2024-01-01' and not unseen(r)]
    selection=[r for r in matched if '2024-01-01'<=r['date']<'2024-07-01']
    calibration=[r for r in matched if '2024-07-01'<=r['date']<'2025-01-01']
    test=[r for r in matched if '2025-01-01'<=r['date']<'2026-01-01']
    counts=dict(zip(('train','selection','calibration','test'),map(len,(train,selection,calibration,test))))
    if min(counts.values())<100:return {'enabled':False,'reason':'Insufficient dated floor-area support','fold_counts':counts},coverage,[]
    base_train=[r for r in sales if '2010-01-01'<=r['date']<'2024-01-01' and not unseen(r)]
    base=fit_base(base_train,FEATURES)
    fits={'Place and road, matched sample':fit(train,False),'Place, road and floor area':fit(train,True)}
    candidates=[{'name':name,'selection':metrics(selection,[predict(model,r) for r in selection])} for name,model in fits.items()]
    selected=min(candidates,key=lambda c:c['selection']['mae'])['name'];model=fits[selected]
    residuals=sorted(abs(math.log(r['price']/predict(model,r))) for r in calibration)
    q=residuals[min(len(residuals)-1,math.ceil((len(residuals)+1)*.8)-1)]
    predictions=[predict(model,r) for r in test]
    for candidate in candidates:candidate['test']=metrics(test,[predict(fits[candidate['name']],r) for r in test])
    # Release only a positive, supported size relation selected before the test.
    enabled=selected=='Place, road and floor area' and 0<model['log_area_coefficient']<2
    final=fit([r for r in matched if '2010-01-01'<=r['date']<'2026-01-01'],selected=='Place, road and floor area')
    final.update(enabled=enabled,log_interval_radius=q,training_end='2025-12-31',
                 training_by_market_type=dict(Counter(r['market_type'] for r in matched if '2010-01-01'<=r['date']<'2026-01-01')),
                 counts=dict(Counter(r['road_type'] for r in matched if '2010-01-01'<=r['date']<'2026-01-01')))
    report={'enabled':enabled,'selected':selected,'fold_counts':counts,'candidates':candidates,
            'test':metrics(test,predictions,q),'base_on_same_sales':metrics(test,[predict_base(base,r) for r in test]),
            'unseen_properties':metrics([r for r in test if unseen(r)],[p for r,p in zip(test,predictions) if unseen(r)],q),
            'by_market':{market:metrics([r for r in test if r['market']==market],[p for r,p in zip(test,predictions) if r['market']==market],q) for market in sorted({r['market'] for r in test})},
            'evaluation_area_coefficient':model['log_area_coefficient'],'production_area_coefficient':final['log_area_coefficient'],
            'log_interval_radius':q,'bedroom_coefficient':None,'maximum_certificate_age_years':5,
            'design':'Train through 2023 excluding 15% of properties. Select early 2024. Calibrate late 2024. Test 2025. Production refit through 2025.',
            'caveat':'Retrospective revised-snapshot conditional valuation with observed HPI. Certificates must be lodged by each sale date. EPC area is not an estate-agent floor-plan measurement. Bedrooms are not modelled.'}
    heldout=[{'id':r['id'],'date':r['date'],'market':r['market'],'actual':r['price'],'predicted':p,
              'area_m2':r['area_m2'],'attribute_date':r['attribute_date'],'attribute_available_date':r['attribute_available_date'],
              'base_prediction':predict_base(base,r)} for r,p in zip(test,predictions)]
    return {'model':final,'evaluation':report},coverage,heldout


def main():
    p=argparse.ArgumentParser();p.add_argument('--sales',type=Path,required=True);p.add_argument('--attributes',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    result,coverage,heldout=evaluate(json.loads(a.sales.read_text()),json.loads(a.attributes.read_text()))
    for name,data in [('area-result',result),('area-coverage',coverage),('area-heldout',heldout)]:
        (a.output/(name+'.json')).write_text(json.dumps(data,indent=2))
    print(json.dumps(result.get('evaluation',result),indent=2))


if __name__=='__main__':main()
