"""Build an auditable offline catalog; inputs are downloaded primary-source snapshots.

Requires openpyxl only to rebuild, not on the Coral. PDF input is pdftotext -layout.
No fuzzy name matching and no automatic translation.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import zipfile


def normalized(value):
    text = unicodedata.normalize('NFKD', value.casefold().replace('grey','gray'))
    return ''.join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('model_zip','ebird_xlsx','taxonomy_csv','birdnet_br','aves_text','output'):
        parser.add_argument('--'+key.replace('_','-'),required=True,type=Path)
    parser.add_argument('--aves-previous-text', type=Path)
    args=parser.parse_args()
    import openpyxl
    book=openpyxl.load_workbook(args.ebird_xlsx,read_only=True,data_only=True)
    rows=book['Sparse'].iter_rows(values_only=True); headers=next(rows)
    keys=['sci_name','category','primary_com_name','Portuguese, Brazil','Portuguese, Portugal','Portuguese, Angola']
    indexes=[headers.index(k) for k in keys];ebird={}
    for row in rows:
        record=dict(zip(keys,[row[i] for i in indexes]))
        if record['category']=='species': ebird[record['sci_name']]=record
    book.close()
    taxonomy={r['scientific_name']:r for r in csv.DictReader(args.taxonomy_csv.open())}
    old=dict(line.split('_',1) for line in args.birdnet_br.read_text().splitlines())
    pdf={}
    pdf_text = ((args.aves_previous_text.read_text() + '\n') if args.aves_previous_text else '') + args.aves_text.read_text()
    for line in pdf_text.splitlines():
        match=re.match(r'^([A-Z][a-z]+ [a-z][a-z-]+)\s{2,}(.+)$',line.strip())
        if match: pdf[match[1]]=match[2].strip()
    with zipfile.ZipFile(args.model_zip) as archive:
        labels=archive.read('labels/en_us.txt')
    model=dict(line.split('_',1) for line in labels.decode().splitlines())
    # Only public synonym links whose English name still matches the model concept
    # are followed. This avoids assigning a lumped taxon's name to a distinct label.
    aliases=collections.defaultdict(list)
    for key,row in taxonomy.items():
        for alias in row['scientific_name_aliases'].split('|'):
            if alias: aliases[alias].append(key)
    sounds={'Dog':'cachorro','Engine':'motor','Environmental':'som ambiente','Fireworks':'fogos de artifício',
            'Gun':'disparo','Human non-vocal':'som humano não vocal','Human vocal':'voz humana',
            'Human whistle':'assobio humano','Noise':'ruído','Power tools':'ferramentas elétricas','Siren':'sirene'}

    def candidates(scientific, english):
        row=ebird.get(scientific,{})
        yield row.get('Portuguese, Brazil'), 'pt-BR', 'ebird_2026_pt_BR'
        value=old.get(scientific)
        if value and normalized(value)!=normalized(english):
            yield value, 'pt', 'birdnet_v2_pt_BR'  # Upstream locale includes Portuguese fallbacks.
        tax=taxonomy.get(scientific,{})
        yield tax.get('common_name_pt'), 'pt', 'birdnet_taxonomy_2026'
        yield row.get('Portuguese, Portugal'), 'pt-PT', 'ebird_2026_pt_PT'
        yield row.get('Portuguese, Angola'), 'pt-AO', 'ebird_2026_pt_AO'
        yield pdf.get(scientific), 'pt-PT', 'aves_do_mundo_2023_2024'

    english_index=collections.defaultdict(list)
    for key,row in taxonomy.items():
        english_index[normalized(row['common_name'])].append(key)
    entries={};unresolved=[];alias_report=[]
    for scientific,english in model.items():
        related=[scientific]
        tax=taxonomy.get(scientific)
        if tax is None:
            targets=aliases.get(scientific,[])
            if len(targets)==1 and (normalized(taxonomy[targets[0]]['common_name'])==normalized(english)
                                   or targets[0].split()[-1]==scientific.split()[-1]):
                tax=taxonomy[targets[0]];related.append(targets[0])
            if tax is None:
                # Unique exact English common-name correspondence, no fuzzy matching.
                targets=english_index.get(normalized(english),[])
                if len(targets)==1:
                    tax=taxonomy[targets[0]];related.append(targets[0])
        if tax:
            # Aliases for the same accepted taxon include earlier genus combinations.
            # Restrict to the same epithet, avoiding splits/lumps with other epithets.
            related.extend(a for a in tax['scientific_name_aliases'].split('|')
                           if a and a.split()[-1]==scientific.split()[-1])
        related=list(dict.fromkeys(related))
        group=tax['taxon_group'] if tax else ('Aves' if any(s in pdf or s in ebird for s in related) else 'unknown')
        selected=None
        # Prefer Brazilian names across known equivalent genus spellings first.
        for s in related:
            name=ebird.get(s,{}).get('Portuguese, Brazil')
            if name: selected=(name,'pt-BR','ebird_2026_pt_BR',s);break
        if not selected:
            for s in related:
                for name,language,source in candidates(s,english):
                    if name and normalized(name)!=normalized(english):
                        selected=(name,language,source,s);break
                if selected:break
        if scientific=='Phylloscopus occisinensis':
            selected=('felosa-de-chingai','pt-PT','avibase_CD3F3594C9FB5D10',scientific);group='Aves'
        if scientific=='Miogryllus saussurei': group='Insecta'
        if scientific in sounds:
            selected=(sounds[scientific],'pt-BR','sound_labels',scientific);group='sound'
        if not selected:
            # An identical indigenous/common word is legitimate only in an explicit
            # Portuguese source, never by relabeling an English fallback as Portuguese.
            for s in related:
                if s in pdf: selected=(pdf[s],'pt-PT','aves_do_mundo_2023_2024',s);break
        if selected:
            name,language,source,matched=selected
            entries[scientific]=dict(name=name.lower(),language=language,source=source,
                                     matched_scientific=matched,taxon_group=group)
            if matched!=scientific:alias_report.append(dict(model=scientific,matched=matched,source=source))
        else:
            entries[scientific]=dict(name=english,language='en',source='model_fallback',
                                     matched_scientific=scientific,taxon_group=group)
            unresolved.append(dict(scientific_name=scientific,english=english,taxon_group=group))
    counts=collections.Counter(r['source'] for r in entries.values())
    report=dict(total=len(entries),portuguese=sum(r['language'].startswith('pt') for r in entries.values()),
                birds=sum(r['taxon_group']=='Aves' for r in entries.values()),
                birds_portuguese=sum(r['taxon_group']=='Aves' and r['language'].startswith('pt') for r in entries.values()),
                sources=dict(counts),unresolved=unresolved,aliases=alias_report)
    snapshots={k:hashlib.sha256(getattr(args,k).read_bytes()).hexdigest()
               for k in ('model_zip','ebird_xlsx','taxonomy_csv','birdnet_br','aves_text')}
    args.output.mkdir(parents=True,exist_ok=True)
    if args.aves_previous_text:
        snapshots['aves_previous_text']=hashlib.sha256(args.aves_previous_text.read_bytes()).hexdigest()
    catalog=dict(schema=1,model='BirdNET-2.4-FP16',labels_sha256=hashlib.sha256(labels).hexdigest(),
                 source_sha256=snapshots,entries=entries)
    (args.output/'bird_names_pt.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
    (args.output/'coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('aliases','unresolved')},ensure_ascii=False))
    print('Unresolved:',len(unresolved))


if __name__=='__main__':main()
