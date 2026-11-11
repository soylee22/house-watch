import csv
import tempfile
import unittest
import math
import json
from importlib.util import find_spec
from pathlib import Path

from core import comparable_sales, connect, import_sales
from research_data import classify_market


class GeographyTest(unittest.TestCase):
    def test_postal_town_is_not_a_market_boundary(self):
        self.assertEqual(classify_market('FLITWICK','BEDFORD')[0],'Flitwick')
        self.assertIsNone(classify_market('AMPTHILL','BEDFORD')[0])
        self.assertEqual(classify_market('LINSLADE','LEIGHTON BUZZARD')[0],'Linslade')
        self.assertEqual(classify_market('','LEIGHTON BUZZARD')[0],'Leighton Buzzard context')
        self.assertEqual(classify_market('HARWELL','DIDCOT')[0],'Didcot surrounds')

    def test_original_geography_comparables_and_out_of_scope_deletions(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);source=state/'sales.csv'
            row=['id-1','475000','2024-01-02','MK45 1AA','D','N','F','1','','THE CROFT','FLITWICK','BEDFORD','CENTRAL BEDFORDSHIRE','BEDFORDSHIRE','A','A']
            def write(r):
                with source.open('w',newline='') as f:csv.writer(f).writerow(r)
            write(row)
            with connect(state) as db:
                self.assertEqual(import_sales(db,[source]),1)
                self.assertEqual(db.execute('SELECT town FROM transactions').fetchone()[0],'BEDFORD')
                self.assertEqual(db.execute('SELECT locality,market FROM transaction_geography').fetchone()[:],('FLITWICK','Flitwick'))
                found=comparable_sales(db,{'town':'Flitwick','house_type':'detached','title':'The Croft, Flitwick'})
                self.assertEqual(len(found['rows']),1)
                self.assertEqual(import_sales(db,[source]),1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],1)
                moved=row.copy();moved[10]='AMPTHILL';write(moved)
                import_sales(db,[source])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM transaction_geography').fetchone()[0],0)
                write(row);import_sales(db,[source])
                deleted=row.copy();deleted[4]='O';deleted[10]='';deleted[11]='ELSEWHERE';deleted[15]='D';write(deleted)
                import_sales(db,[source])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)


@unittest.skipUnless(find_spec('requests'),'Research HTTP dependencies are not installed')
class RefreshTest(unittest.TestCase):
    def test_hpi_release_uses_govuk_publication_metadata(self):
        from research_pipeline import refresh_hpi
        from unittest.mock import patch
        from types import SimpleNamespace
        collection='<a href="/government/statistical-data-sets/example">UK House Price Index: data downloads August 2026</a>'
        page='<meta name="govuk:first-published-at" content="2026-10-21T10:17:24+01:00"><a href="https://publicdata.landregistry.gov.uk/example.csv">Average price by property type</a>'
        def response(text='',content=b'csv'):
            return SimpleNamespace(text=text,content=content,raise_for_status=lambda:None)
        with tempfile.TemporaryDirectory() as folder:
            with patch('requests.get',side_effect=[response(collection),response(page),response()]):
                refresh_hpi(Path(folder))
            m=json.loads((Path(folder)/'manifest.json').read_text())
            self.assertEqual(m['release_date'],'2026-10-21')
            self.assertEqual(m['observation_end'],'2026-08')


@unittest.skipUnless(find_spec('sklearn'),'Research dependencies are not installed')
class ModelTest(unittest.TestCase):
    def test_public_export_excludes_household_canaries(self):
        from build_research_site import build
        from price_model import AREA,TYPE_NAMES
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'state';models=root/'models';models.mkdir()
            secret='PRIVATE-HOUSEHOLD-CANARY-DO-NOT-PUBLISH'
            with connect(state) as db:
                db.execute('INSERT INTO properties VALUES(?,?)',('private-id','2026-11-11'))
                db.execute('INSERT INTO feedback VALUES(?,?,?,?,?)',('private-id','Lee','like',secret,'2026-11-11'))
                db.execute('INSERT INTO messages VALUES(?,?,?,?,?)',('private-mail','2026-11-11',secret,1,''))
                db.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('public-id',400000,'2020-01-01','OX11 7AA','D','N','F','1','','PUBLIC ROAD','DIDCOT','SOUTH OXFORDSHIRE','A','fixture'))
                db.execute('INSERT INTO transaction_geography VALUES(?,?,?,?,?)',('public-id','DIDCOT','DIDCOT','Didcot','fixture'))
            (state/'settings.json').write_text(json.dumps({'recipients':[secret]}))
            hpi=root/'hpi.csv'
            names=['Date','Region_Name']+[name+'_Index' for name in TYPE_NAMES.values()]
            with hpi.open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=names);writer.writeheader()
                for area in set(AREA.values()):writer.writerow({'Date':'2020-01-01','Region_Name':area}|{name+'_Index':100 for name in TYPE_NAMES.values()})
            (models/'profile.json').write_text(json.dumps({'by_market':{'Didcot':1},'source_snapshot':'2026-11-11','hpi_release':'2026-10-21'}))
            for name in ['model','evaluation']:(models/(name+'.json')).write_text('{}')
            destination=root/'public';build(state,hpi,models,destination)
            self.assertFalse(any(secret in p.read_text() for p in destination.rglob('*') if p.is_file()))
            self.assertFalse((destination/'settings.json').exists())
            sale=json.loads((destination/'data'/'didcot.json').read_text())[0]
            self.assertEqual(sale[3],'PUBLIC ROAD')

    def test_final_test_prices_do_not_choose_model_or_calibrate_range(self):
        from price_model import enrich,evaluate
        rows=[]
        for year in range(2010,2026):
            for month in range(1,13):
                for i in range(25):
                    r=enrich({'id':f'{year}-{month}-{i}','date':f'{year}-{month:02}-01',
                              'market':'Didcot','type':'D','tenure':'F','new_build':'N',
                              'number':str(i),'unit':'','street':'ROAD '+str(i%3),
                              'postcode':'OX11 7AA','hpi':100,'price':300000+i*1000})
                    rows.append(r)
        _,a,heldout=evaluate(rows)
        changed=[r|{'price':r['price']*2} if r['date'].startswith('2025') else r for r in rows]
        _,b,_=evaluate(changed)
        self.assertEqual(a['selected'],b['selected'])
        self.assertEqual(a['log_interval_radius'],b['log_interval_radius'])
        self.assertNotEqual(a['test']['mae'],b['test']['mae'])
        self.assertTrue(all(r['date'].startswith('2025') for r in heldout))
        self.assertGreater(a['unseen_properties']['n'],0)

    def test_time_input_required_and_sparse_locations_fall_back(self):
        from price_model import enrich,fit,predict
        row=enrich({'market':'Didcot','type':'D','tenure':'F','new_build':'N','date':'2020-01-01',
                    'number':'1','unit':'','street':'OAK ROAD','postcode':'OX11 7AA','price':500000,'hpi':100})
        model=fit([row]*20,['market_type','road_type','period'])
        self.assertAlmostEqual(predict(model,row),500000,places=3)
        unknown=enrich(row|{'street':'UNSEEN ROAD','date':'2026-01-01'})
        self.assertTrue(math.isfinite(predict(model,unknown)))
        with self.assertRaises(ValueError):predict(model,row|{'hpi':0})


if __name__=='__main__':unittest.main()
