"""Official historical sales acquisition and explicit market geography.

This module never reads mail, preferences, recipients or the private shortlist.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path


ENDPOINT = 'https://landregistry.data.gov.uk/landregistry/query'
PREFIX = '''PREFIX lrppi: <http://landregistry.data.gov.uk/def/ppi/>
PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>
'''
TARGETS = {'Didcot': ('town','DIDCOT'), 'Fleet': ('town','FLEET'),
           'Hitchin': ('town','HITCHIN'), 'Leighton-Buzzard': ('town','LEIGHTON BUZZARD'),
           'Flitwick': ('locality','FLITWICK')}
FIELDS = ('paon','saon','street','locality','town','district','county','postcode')


def classify_market(locality, postal_town):
    locality=(locality or '').upper().strip()
    town=(postal_town or '').upper().strip()
    # Locality outranks postal town. Preserve both original fields separately.
    if locality=='FLITWICK' or town=='FLITWICK':
        return 'Flitwick','explicit locality or postal town'
    if locality=='LINSLADE' or town=='LINSLADE':
        return 'Linslade','explicit locality or postal town'
    for name in ('Didcot','Fleet','Hitchin'):
        if town==name.upper():
            if locality and locality!=town:
                return name+' surrounds','postal town with different locality'
            return name,'postal town, no conflicting locality'
    if town=='LEIGHTON BUZZARD':
        return 'Leighton Buzzard context','postal town does not establish Linslade'
    return None,None


def query(text):
    import requests
    for attempt in range(3):
        try:
            response=requests.get(ENDPOINT,params={'query':PREFIX+text,'output':'csv'},
                                  headers={'User-Agent':'HouseWatch-research/1.0'},timeout=90)
            response.raise_for_status()
            if 'text/csv' not in response.headers.get('Content-Type',''):
                raise ValueError('Expected official CSV query response')
            return response.content
        except requests.RequestException:
            if attempt==2:raise
            time.sleep(2*(attempt+1))


def acquire(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for name,(field,value) in TARGETS.items():
        path=destination/(name.lower()+'.csv')
        entry=destination/(name.lower()+'.json')
        if path.exists() and entry.exists():
            saved=json.loads(entry.read_text())
            if hashlib.sha256(path.read_bytes()).hexdigest()!=saved['sha256']:
                raise ValueError('Existing immutable source hash mismatch')
            manifest.append(saved);print(name,'cached',saved['rows'],flush=True);continue
        where=f'''?addr lrcommon:{field} "{value}" .
        ?trans lrppi:propertyAddress ?addr ; lrppi:transactionId ?id ;
          lrppi:pricePaid ?price ; lrppi:transactionDate ?date ;
          lrppi:propertyType ?type ; lrppi:estateType ?estate ;
          lrppi:newBuild ?new ; lrppi:transactionCategory ?category .
        VALUES ?type {{ lrcommon:detached lrcommon:semi-detached lrcommon:terraced }}
        OPTIONAL {{ ?trans lrppi:recordStatus ?status }}
        FILTER(!BOUND(?status) || ?status != lrppi:delete)
        '''
        count_rows=list(csv.DictReader(io.StringIO(query('SELECT (COUNT(DISTINCT ?trans) AS ?n) WHERE {'+where+'}').decode())))
        expected=int(count_rows[0]['n']);rows=[];raw_hashes=[]
        optional='\n'.join(f'OPTIONAL {{ ?addr lrcommon:{f} ?{f} }}' for f in FIELDS)
        for offset in range(0,expected,5000):
            body=query('SELECT ?id ?price ?date ?type ?estate ?new ?category '+
                       ' '.join('?'+f for f in FIELDS)+' WHERE {'+where+optional+
                       f'}} ORDER BY ?id LIMIT 5000 OFFSET {offset}')
            raw_hashes.append(hashlib.sha256(body).hexdigest())
            for item in csv.DictReader(io.StringIO(body.decode('utf-8-sig'))):
                kind={'detached':'D','semi-detached':'S','terraced':'T'}[item['type'].rsplit('/',1)[-1]]
                tenure={'freehold':'F','leasehold':'L'}.get(item['estate'].rsplit('/',1)[-1],'U')
                rows.append(['{'+item['id'].upper()+'}',item['price'],item['date'],item['postcode'],kind,
                             'Y' if item['new'].lower() in ('true','1') else 'N',tenure,
                             item['paon'],item['saon'],item['street'],item['locality'],item['town'],
                             item['district'],item['county'],
                             'A' if item['category'].endswith('/standardPricePaidTransaction') else 'B','A'])
            print(name, min(offset+5000,expected),'/',expected,flush=True)
        if len(rows)!=expected or len({r[0] for r in rows})!=expected:
            raise ValueError(f'{name}: query count or unique-ID reconciliation failed')
        temp=path.with_suffix('.part')
        with temp.open('w',newline='') as f:csv.writer(f).writerows(rows)
        temp.replace(path)
        meta={'file':path.name,'source':ENDPOINT,'filter':{field:value},'rows':len(rows),
              'expected_count':expected,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'response_sha256':raw_hashes,'retrieved':datetime.now(timezone.utc).isoformat(),
              'format':'PPD column projection of official current linked-data records',
              'coverage':'All current returned D/S/T records for this selector, not all nearby postcodes'}
        entry.write_text(json.dumps(meta,indent=2));manifest.append(meta)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination',type=Path)
    args=p.parse_args();acquire(args.destination)
