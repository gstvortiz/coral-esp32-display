"""Offline popular names indexed by immutable model scientific labels."""
import hashlib
import json
from pathlib import Path


class BirdNames:
    def __init__(self, catalog=None, overrides=None):
        path = Path(catalog) if catalog else Path(__file__).parent / 'data' / 'bird_names_pt.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        self.entries, self.labels_sha256 = data['entries'], data['labels_sha256']
        override_path = Path(overrides) if overrides else path.with_name('name_overrides.json')
        if override_path.exists():
            for scientific, name in json.loads(override_path.read_text(encoding='utf-8')).items():
                if scientific not in self.entries or not isinstance(name, str) or not 0<len(name)<=128:
                    raise ValueError('Nome personalizado invalido: ' + scientific)
                self.entries[scientific] = dict(self.entries[scientific], name=name, language='pt-BR', source='local_override')

    def check_labels(self, classifier_labels):
        data = Path(classifier_labels).read_bytes()
        if hashlib.sha256(data).hexdigest() != self.labels_sha256:
            raise ValueError('Catalogo nao corresponde aos rotulos do modelo instalado')
        keys = [line.split('_', 1)[0] for line in data.decode('utf-8').splitlines()]
        if len(keys) != len(self.entries) or set(keys) != set(self.entries):
            raise ValueError('Catalogo incompleto')

    def localize(self, result):
        localized = dict(result)
        for key in ('detections', 'candidates', 'other_sounds'):
            if key not in result:
                continue
            localized[key] = []
            for item in result[key]:
                item = dict(item)
                entry = self.entries.get(item['scientific_name'])
                if entry:
                    item.update(name=entry['name'], name_language=entry['language'], name_source=entry['source'])
                localized[key].append(item)
        return localized
