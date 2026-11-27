import json
from pathlib import Path
import tempfile
import unittest
from sub.bird_names import BirdNames
from pub.birds import observation
from sub.subscriber import parse_message

class NameTests(unittest.TestCase):
    def test_all_birds_have_portuguese_and_preserve_identity(self):
        names=BirdNames()
        self.assertEqual(len(names.entries),6522)
        birds=[v for v in names.entries.values() if v['taxon_group']=='Aves']
        self.assertEqual(len(birds),6421)
        self.assertTrue(all(v['language'].startswith('pt') for v in birds))
        self.assertFalse(any(v['taxon_group']=='unknown' for v in names.entries.values()))
        source=dict(detections=[dict(scientific_name='Pitangus sulphuratus',name='Great Kiskadee',score=.8)])
        result=names.localize(source)
        self.assertEqual(result['detections'][0]['name'],'bem-te-vi')
        self.assertEqual(result['detections'][0]['scientific_name'],'Pitangus sulphuratus')
        self.assertEqual(source['detections'][0]['name'],'Great Kiskadee')
        result=names.localize(dict(detections=[dict(scientific_name='Turdus rufiventris',name='x',score=.8)]))
        self.assertEqual(parse_message(json.dumps(observation(result)).encode())['name'],'sabia-laranjeira')

    def test_overrides_and_wrong_model_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'overrides.json'
            path.write_text(json.dumps({'Pitangus sulphuratus':'bem-te-vi daqui'}))
            self.assertEqual(BirdNames(overrides=path).entries['Pitangus sulphuratus']['name'],'bem-te-vi daqui')
            path.write_text(json.dumps({'not a species':'inventado'}))
            with self.assertRaises(ValueError): BirdNames(overrides=path)
            path.write_text('not the model labels')
            with self.assertRaises(ValueError): BirdNames().check_labels(path)

if __name__=='__main__': unittest.main()
