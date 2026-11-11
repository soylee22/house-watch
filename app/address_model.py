"""Exact-address prior-sale evidence with a separately evaluated blend.

No bedroom, floor-area or renovation premium is inferred from missing data.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

from price_model import predict, metrics

WEIGHTS=(0.0,0.25,0.5,0.75,1.0)


def age_band(years):
    return '1 to 5 years' if years<=5 else '5 to 10 years' if years<=10 else '10 to 20 years' if years<=20 else 'Over 20 years'


def prior_pairs(rows):
    """Use only the latest strictly earlier sale, with a one-year minimum gap."""
    histories=defaultdict(list);pairs=[]
    for current in sorted(rows,key=lambda r:(r['date'],r.get('id',''))):
        old=histories[current['property_id']]
        before=[r for r in old if r['date']<current['date']]
        if before:
            latest=before[-1]
            same_date=[r for r in before if r['date']==latest['date']]
            days=(date.fromisoformat(current['date'])-date.fromisoformat(latest['date'])).days
            # A very recent flip, changed type/tenure or ambiguous sale needs review.
            if (days>=365 and latest['type']==current['type'] and latest['tenure']==current['tenure']
                    and len({r['price'] for r in same_date})==1 and current['new_build']=='N'):
                pairs.append((current,latest,days/365.25))
        old.append(current)
    return pairs


def anchor_price(model,current,previous):
    # The ratio adjusts time and supported recorded characteristics, including
    # removal of a prior new-build premium when valuing an established house.
    return previous['price']*predict(model,current)/predict(model,previous)


def blend(base,anchor,weight):
    return math.exp((1-weight)*math.log(base)+weight*math.log(anchor))


def finite_radius(errors):
    errors=sorted(errors)
    return errors[min(len(errors)-1,math.ceil((len(errors)+1)*.8)-1)]


def evaluate_address_model(model,rows):
    pairs=prior_pairs(rows)
    selection=[p for p in pairs if '2024-01-01'<=p[0]['date']<'2024-07-01']
    calibration=[p for p in pairs if '2024-07-01'<=p[0]['date']<'2025-01-01']
    test=[p for p in pairs if '2025-01-01'<=p[0]['date']<'2026-01-01']
    if min(map(len,(selection,calibration,test)))<100:
        return {'enabled':False,'reason':'Insufficient repeated-sale fold support'},None
    def estimate(p,w):
        current,previous,_=p
        return blend(predict(model,current),anchor_price(model,current,previous),w)
    def choose(sample):
        return min(WEIGHTS,key=lambda w:sum(abs(estimate(p,w)-p[0]['price']) for p in sample))
    global_weight=choose(selection);weights={}
    for band in ('1 to 5 years','5 to 10 years','10 to 20 years','Over 20 years'):
        sample=[p for p in selection if age_band(p[2])==band]
        weights[band]={'weight':choose(sample) if len(sample)>=100 else global_weight,
                       'selection_n':len(sample),'pooled':len(sample)<100}
    def predicted(p):return estimate(p,weights[age_band(p[2])]['weight'])
    errors=[abs(math.log(p[0]['price']/predicted(p))) for p in calibration]
    q=finite_radius(errors)
    radii={}
    for band in weights:
        sample=[p for p in calibration if age_band(p[2])==band]
        radii[band]={'log_radius':finite_radius([abs(math.log(p[0]['price']/predicted(p))) for p in sample]) if len(sample)>=100 else q,
                     'calibration_n':len(sample),'pooled':len(sample)<100}
    actual=[p[0] for p in test];base=[predict(model,p[0]) for p in test]
    pred=[predicted(p) for p in test]
    report={'enabled':True,'minimum_gap_days':365,'weights':weights,'intervals':radii,
            'global_weight':global_weight,'log_interval_radius':q,
            'fold_counts':{'selection':len(selection),'calibration':len(calibration),'test':len(test)},
            'test':metrics(actual,pred,q),'base_on_same_sales':metrics(actual,base),
            'by_age':{},'by_market':{},
            'design':'Base fit ends in 2023. Select prior-sale weights on Jan–Jun 2024. Calibrate on Jul–Dec 2024. Evaluate on 2025 using only an earlier same-address sale at least one year old.',
            'caveat':'Retrospective revised-snapshot assessment. Previous sale, unchanged address/type/tenure and dated HPI are required. Physical changes remain unmeasured. This is not a forecast or a bedroom adjustment.'}
    # Report actual coverage of the age-specific intervals used in the calculator.
    report['age_interval_coverage']=sum(
        abs(math.log(p[0]['price']/v))<=radii[age_band(p[2])]['log_radius'] for p,v in zip(test,pred))/len(test)
    report['test']['interval_coverage']=report['age_interval_coverage']
    widths=sorted(v*(math.exp(radii[age_band(p[2])]['log_radius'])-math.exp(-radii[age_band(p[2])]['log_radius'])) for p,v in zip(test,pred))
    report['test']['median_interval_width']=(widths[(len(widths)-1)//2]+widths[len(widths)//2])/2
    for name,field in (('by_age',lambda p:age_band(p[2])),('by_market',lambda p:p[0]['market'])):
        for key in sorted({field(p) for p in test}):
            sample=[(p,v) for p,v in zip(test,pred) if field(p)==key]
            report[name][key]=metrics([p[0] for p,v in sample],[v for p,v in sample])
            report[name][key]['interval_coverage']=sum(abs(math.log(p[0]['price']/v))<=radii[age_band(p[2])]['log_radius'] for p,v in sample)/len(sample)
    report['_heldout']={p[0].get('id',p[0]['property_id']+'|'+p[0]['date']):{
        'address_predicted':round(v,2),'previous_sale_date':p[1]['date'],
        'previous_sale_price':p[1]['price'],'prior_sale_weight':weights[age_band(p[2])]['weight'],
        'address_log_interval_radius':radii[age_band(p[2])]['log_radius']}
        for p,v in zip(test,pred)}
    config={k:report[k] for k in ('enabled','minimum_gap_days','weights','intervals','log_interval_radius')}
    return config,report
