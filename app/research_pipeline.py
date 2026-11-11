"""Public-only research rebuild. No household state or mail credentials are used."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin,urlsplit

import requests
from bs4 import BeautifulSoup

from research_data import acquire
from price_model import build as build_model
from build_research_site import build as build_site, write_manifest


def refresh_hpi(destination):
    collection='https://www.gov.uk/government/collections/uk-house-price-index-reports'
    response=requests.get(collection,timeout=40);response.raise_for_status()
    links=[]
    for a in BeautifulSoup(response.text,'html.parser').find_all('a',href=True):
        match=re.search(r'data downloads ([A-Za-z]+) (\d{4})',a.get_text(' ',strip=True),re.I)
        if match:links.append((datetime.strptime(' '.join(match.groups()),'%B %Y'),urljoin(collection,a['href'])))
    if not links:raise ValueError('Latest official HPI download page not found')
    month,page=max(links)
    response=requests.get(page,timeout=40);response.raise_for_status()
    soup=BeautifulSoup(response.text,'html.parser')
    candidates=[urljoin(page,a['href']) for a in soup.find_all('a',href=True) if 'average price by property type' in a.get_text(' ',strip=True).lower()]
    if len(candidates)!=1:raise ValueError('Ambiguous HPI property-type download')
    url=candidates[0]
    if urlsplit(url).hostname!='publicdata.landregistry.gov.uk':raise ValueError('Unexpected official HPI download host')
    response=requests.get(url,timeout=120);response.raise_for_status()
    date=soup.find('meta',attrs={'property':'article:published_time'})
    if date:release=date['content'][:10]
    else:
        tag=soup.find('time',attrs={'datetime':True})
        if not tag:raise ValueError('Official HPI release date not found')
        release=tag['datetime'][:10]
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'property-type.csv').write_bytes(response.content)
    (destination/'manifest.json').write_text(json.dumps({'source':url,'sha256':hashlib.sha256(response.content).hexdigest(),
            'release_date':release,'observation_end':month.strftime('%Y-%m'),'retrieved':datetime.now(timezone.utc).isoformat()},indent=2))


def run(inputs,docs,refresh=False):
    inputs=Path(inputs);docs=Path(docs)
    if refresh:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);acquire(root/'ppd');refresh_hpi(root/'hpi')
            for folder in ('ppd','hpi'):
                (inputs/folder).mkdir(parents=True,exist_ok=True)
                for path in (root/folder).iterdir():shutil.copy2(path,inputs/folder/path.name)
    manifest=json.loads((inputs/'ppd'/'manifest.json').read_text())
    sources=[]
    for meta in manifest:
        path=inputs/'ppd'/meta['file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('Source snapshot failed checksum')
        sources.append(path)
    hpi=inputs/'hpi'/'property-type.csv'
    hpi_meta=json.loads((hpi.parent/'manifest.json').read_text())
    if hashlib.sha256(hpi.read_bytes()).hexdigest()!=hpi_meta['sha256']:raise ValueError('HPI snapshot failed checksum')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        build_model(root/'state',sources,hpi,root/'models')
        build_site(root/'state',hpi,root/'models',docs)
        # Published evaluation is reproducible without any private household data.
        for name in ('evaluation.json','profile.json'):
            shutil.copy2(root/'models'/name,docs/'data'/name)
    shutil.copy2(inputs/'ppd'/'manifest.json',docs/'data'/'source-manifest.json')
    shutil.copy2(inputs/'hpi'/'manifest.json',docs/'data'/'hpi-manifest.json')
    write_manifest(docs)
    print(json.dumps({'public_site':str(docs),'household_state_accessed':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--docs',type=Path,required=True);p.add_argument('--refresh',action='store_true')
    a=p.parse_args();run(a.inputs,a.docs,a.refresh)
