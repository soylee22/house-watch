"""Dated physical evidence. Raw EPC addresses and unrelated fields stay private.

Only exact, unique PPD address matches are accepted. A certificate lodged after
a sale cannot describe that sale in a temporal evaluation. Habitable rooms are
never converted to bedrooms.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


def property_id(row):
    key='|'.join(str(row.get(k,'')).strip().upper() for k in ('postcode','number','unit','street'))
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def normal_address(value):
    # Keep token boundaries: house 1, unit 2 must not become house 12.
    return ' '.join(re.sub(r'[^A-Z0-9]+',' ',str(value).upper()).split())


def normal_postcode(value):
    return re.sub(r'\s+','',str(value).upper())


def iso_date(value):
    try:
        result=str(value).strip()[:10]
        date.fromisoformat(result)
        return result
    except ValueError:
        return None


def fields(row):
    return {re.sub(r'[^a-z0-9]+','_',str(k).lower()).strip('_'):str(v or '').strip() for k,v in row.items()}


def csv_rows(path):
    path=Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members=[n for n in archive.namelist() if n.lower().endswith('.csv') and 'recommend' not in n.lower()]
            if not members:raise ValueError('No certificate CSV in archive')
            for member in members:
                with archive.open(member) as binary:
                    yield from csv.DictReader(io.TextIOWrapper(binary,encoding='utf-8-sig',newline=''))
    else:
        with path.open(encoding='utf-8-sig',newline='') as stream:
            yield from csv.DictReader(stream)


def address_lookup(sales):
    lookup=defaultdict(set);properties={}
    for row in sales:
        pid=property_id(row);properties[pid]=row
        address=normal_address(' '.join(str(row.get(k) or '') for k in ('unit','number','street')))
        if address and row.get('number') and row.get('postcode'):
            lookup[(normal_postcode(row['postcode']),address)].add(pid)
    return lookup,properties


def match_epc(row,lookup):
    postcode=normal_postcode(row.get('postcode',''));parts=[row.get('address'+str(i),'') for i in (1,2,3)]
    if not any(parts) and row.get('address'):parts=[row['address']]
    matches=set()
    for length in range(1,len(parts)+1):
        matches.update(lookup.get((postcode,normal_address(' '.join(parts[:length]))),()))
    return next(iter(matches)) if len(matches)==1 else None


def finite_number(value,low,high):
    try:
        number=float(value)
        return number if low<=number<=high else None
    except (ValueError,TypeError):
        return None


def epc_observation(row,pid):
    inspected=iso_date(row.get('inspection_date'));lodged=iso_date(row.get('lodgement_date') or row.get('lodgement_datetime'))
    certificate=row.get('certificate_number') or row.get('lmk_key')
    if not inspected or not lodged or not certificate or lodged<inspected:return None
    area=finite_number(row.get('total_floor_area'),20,1000)
    if area is None:return None
    rooms=finite_number(row.get('number_habitable_rooms'),1,30)
    return {'property_id':pid,'source':'official EPC','certificate_id':certificate,
            'inspection_date':inspected,'available_date':lodged,'area_m2':area,
            'habitable_rooms':int(rooms) if rooms and rooms.is_integer() else None,
            'energy_rating':row.get('current_energy_rating') if row.get('current_energy_rating') in tuple('ABCDEFG') else None,
            'built_form':row.get('built_form',''),'property_type':row.get('property_type',''),
            'uprn':row.get('uprn',''),'bedrooms':None,
            'area_basis':'EPC total internal floor area'}


def import_epc(paths,sales):
    lookup,properties=address_lookup(sales);observations={};counts=Counter();by_market=Counter()
    sources=[]
    for path in paths:
        path=Path(path)
        with path.open('rb') as stream:
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        sources.append({'file':path.name,'sha256':digest,'bytes':path.stat().st_size})
        for raw in csv_rows(path):
            counts['source_rows']+=1;row=fields(raw)
            pid=match_epc(row,lookup)
            if not pid:counts['unmatched_or_ambiguous']+=1;continue
            counts['exact_address_rows']+=1
            observation=epc_observation(row,pid)
            if not observation:counts['invalid_area_date_or_certificate']+=1;continue
            key=(pid,observation['certificate_id'])
            if key in observations and observations[key]!=observation:
                raise ValueError('Conflicting source records for the same certificate')
            observations[key]=observation
    result=sorted(observations.values(),key=lambda r:(r['property_id'],r['available_date'],r['certificate_id']))
    for pid in {r['property_id'] for r in result}:by_market[properties[pid]['market']]+=1
    report={'counts':dict(counts),'certificates':len(result),'matched_properties':len({r['property_id'] for r in result}),
            'properties_by_market':dict(by_market),'sources':sources,
            'matching':'Exact postcode and complete address prefix, unique PPD identity. No fuzzy or neighbouring-number matches.',
            'bedrooms_available':False,'raw_addresses_exported':False}
    return result,report


def compatible_type(observation,sale):
    kind=observation.get('property_type','').lower();form=observation.get('built_form','').lower()
    if kind and kind not in ('house','bungalow'):return False
    expected='S' if 'semi' in form else 'T' if 'terrace' in form else 'D' if form=='detached' else None
    return expected is None or expected==sale['type']


class AttributeHistory:
    def __init__(self,observations):
        self.history=defaultdict(list)
        for observation in observations:self.history[observation['property_id']].append(observation)
        for history in self.history.values():history.sort(key=lambda x:(x['available_date'],x['inspection_date']))

    def at(self,sale,cutoff=None,max_age_years=5):
        cutoff=cutoff or sale['date'];target=date.fromisoformat(cutoff)
        history=[r for r in self.history.get(property_id(sale),[]) if r['available_date']<=cutoff and r['inspection_date']<=cutoff]
        if not history:return None
        latest=history[-1]
        # Do not skip a conflicting or changed latest record to use an older one.
        peers=[r for r in history if r['available_date']==latest['available_date']]
        if len({(r['area_m2'],r.get('habitable_rooms'),r.get('built_form')) for r in peers})>1:return None
        if (target-date.fromisoformat(latest['inspection_date'])).days>max_age_years*365.25:return None
        if not compatible_type(latest,sale):return None
        return latest


def join_sales(sales,observations):
    history=AttributeHistory(observations);matched=[];coverage=Counter();excluded=Counter()
    for sale in sales:
        observation=history.at(sale)
        if observation:
            matched.append(sale|{'area_m2':observation['area_m2'],'habitable_rooms':observation['habitable_rooms'],
                                 'certificate_id':observation['certificate_id'],'attribute_date':observation['inspection_date'],
                                 'attribute_available_date':observation['available_date']})
            coverage[(sale['market'],sale['date'][:4])]+=1
        else:excluded['no supported certificate available by sale date']+=1
    return matched,{'matched_sales':len(matched),'by_market_year':[{'market':m,'year':y,'sales':n} for (m,y),n in sorted(coverage.items())],
                    'excluded':dict(excluded),'maximum_certificate_age_years':5}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sales',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('epc_files',nargs='+',type=Path)
    args=parser.parse_args();sales=json.loads(args.sales.read_text())
    observations,report=import_epc(args.epc_files,sales);args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'epc-observations.json').write_text(json.dumps(observations,separators=(',',':')))
    (args.output/'attribute-import.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
