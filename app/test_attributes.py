import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from property_attributes import AttributeHistory, address_lookup, epc_observation, fields, import_epc, match_epc, property_id


def sale(**changes):
    return dict(postcode='OX11 7AA',number='12',unit='',street='OAK ROAD',market='Didcot',date='2020-05-01',type='T')|changes


def certificate(**changes):
    return dict(ADDRESS1='12, Oak Road',ADDRESS2='Didcot',POSTCODE='OX11 7AA',CERTIFICATE_NUMBER='1111-2222-3333-4444-5555',
                INSPECTION_DATE='2019-04-01',LODGEMENT_DATE='2019-04-02',TOTAL_FLOOR_AREA='110',NUMBER_HABITABLE_ROOMS='6',
                CURRENT_ENERGY_RATING='C',PROPERTY_TYPE='House',BUILT_FORM='Mid-Terrace')|changes


class AttributeTest(unittest.TestCase):
    def test_matching_keeps_units_and_house_number_boundaries(self):
        rows=[sale(),sale(number='1',unit='2'),sale(number='1A'),sale(number='2',unit='FLAT 1')]
        lookup,_=address_lookup(rows)
        self.assertEqual(match_epc(fields(certificate()),lookup),property_id(rows[0]))
        self.assertEqual(match_epc(fields(certificate(ADDRESS1='2, 1 Oak Road')),lookup),property_id(rows[1]))
        self.assertIsNone(match_epc(fields(certificate(ADDRESS1='1 Oak Road')),lookup))
        self.assertIsNone(match_epc(fields(certificate(POSTCODE='OX11 7AB')),lookup))
        self.assertEqual(match_epc(fields(certificate(ADDRESS1='Flat 1',ADDRESS2='2 Oak Road',ADDRESS3='Didcot')),lookup),property_id(rows[3]))

    def test_no_habitable_rooms_to_bedrooms_conversion_or_unrelated_fields(self):
        observation=epc_observation(fields(certificate(ASSESSOR_EMAIL='PRIVATE-CANARY',BEDROOMS='4')),property_id(sale()))
        self.assertEqual(observation['habitable_rooms'],6)
        self.assertIsNone(observation['bedrooms'])
        self.assertNotIn('PRIVATE-CANARY',str(observation))
        self.assertNotIn('address1',observation)

    def test_future_certificates_stale_records_conflicts_and_type_changes(self):
        pid=property_id(sale())
        before=epc_observation(fields(certificate()),pid)
        after=epc_observation(fields(certificate(CERTIFICATE_NUMBER='future',INSPECTION_DATE='2022-01-01',LODGEMENT_DATE='2022-01-02',TOTAL_FLOOR_AREA='150')),pid)
        history=AttributeHistory([after,before])
        self.assertEqual(history.at(sale())['area_m2'],110)
        self.assertIsNone(history.at(sale(date='2018-01-01')))
        self.assertIsNone(history.at(sale(date='2029-01-01')))
        self.assertIsNone(AttributeHistory([before,before|{'certificate_id':'conflict','area_m2':120}]).at(sale()))
        self.assertIsNone(AttributeHistory([before,before|{'available_date':'2020-04-01','built_form':'Detached'}]).at(sale()))
        self.assertIsNone(epc_observation(fields(certificate(LODGEMENT_DATE='2018-01-01')),pid))

    def test_zip_streaming_deduplicates_and_rejects_bad_measurements(self):
        raw=io.StringIO();writer=csv.DictWriter(raw,fieldnames=certificate().keys());writer.writeheader()
        writer.writerow(certificate());writer.writerow(certificate());writer.writerow(certificate(ADDRESS1='13 Oak Road'))
        writer.writerow(certificate(CERTIFICATE_NUMBER='invalid',TOTAL_FLOOR_AREA='0'))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.zip'
            with zipfile.ZipFile(path,'w') as archive:archive.writestr('certificates.csv',raw.getvalue())
            observations,report=import_epc([path],[sale()])
        self.assertEqual(len(observations),1)
        self.assertEqual(report['counts']['source_rows'],4)
        self.assertEqual(report['counts']['unmatched_or_ambiguous'],1)
        self.assertEqual(report['counts']['invalid_area_date_or_certificate'],1)


if __name__=='__main__':unittest.main()
