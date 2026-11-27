# Nomes populares offline

Catálogo para **as 6.522 classes exatas do BirdNET 2.4 FP16 instalado**.
Gerado em 2026-11-16: 6.421 classes de aves, todas com nome em português.
São priorizados os nomes brasileiros; aves estrangeiras podem ter nomes de
Portugal/Angola ou português sem região definida pela fonte. Isso não significa
que todas as aves do mundo tenham um nome popular brasileiro estabelecido.

`bird_names_pt.json` guarda nome, idioma, fonte e correspondência científica de
cada classe. `coverage.json` registra contagens, sinônimos e 55 classes sem nome
português nas fontes (40 insetos e 15 anfíbios; nenhuma ave). Essas classes
conservam o nome original. O checksum dos rótulos é conferido ao iniciar;
nomes científicos, índices do modelo e scores não são alterados.

## Fontes e atribuição

- Cornell Lab of Ornithology, [eBird Common Names](https://support.ebird.org/en/support/solutions/articles/48000804865), matriz de 27/10/2026,
  [download XLSX](https://cornell.box.com/shared/static/fjp112mh25nlvbyr1p28r9ya7nriblls.xlsx).
  Coluna brasileira prioritária. Algumas entradas agrupam nomes separados por
  `/` devido a diferenças entre a taxonomia brasileira e a do modelo: preservamos
  o agrupamento para não inventar uma identificação mais específica.
- BirdNET Team / Cornell Lab, [BirdNET Taxonomy v0.5, novembro de 2026](https://birdnet.cornell.edu/taxonomy/download),
  [CSV](https://birdnet.cornell.edu/taxonomy/api/download/csv), CC BY-SA 4.0.
  Usamos nomes e sinônimos, com alterações de seleção, normalização para minúsculas
  e combinação com outras referências. Os registros derivados desta fonte
  permanecem sob [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
- BirdNET Team, [rótulos pt_BR do Analyzer v2.0.0](https://raw.githubusercontent.com/birdnet-team/BirdNET-Analyzer/v2.0.0/birdnet_analyzer/labels/V2.4/BirdNET_GLOBAL_6K_V2.4_Labels_pt_BR.txt).
  Entradas ainda em inglês são descartadas como traduções. Essa lista inclui
  alternativas portuguesas, por isso o idioma é registrado como `pt`.
- Paulo Alves, Gonçalo Elias, José Frade, Pedro Nicolau e João Pereira,
  [Aves do Mundo — Lista de nomes portugueses](https://avesdomundo.info/sobre-a-lista/),
  [2023](https://avesdomundo.info/wp-content/uploads/2023/01/aves-do-mundo-lista-de-nomes-portugueses-2023.pdf)
  e [2024](https://avesdomundo.info/wp-content/uploads/2024/10/aves-do-mundo-lista-de-nomes-portugueses-2024.pdf).
  Referência de pares taxonômicos/nome comum; português de Portugal. Os livros,
  textos e ilustrações não são redistribuídos neste projeto.
- Denis Lepage / Birds Canada, [Avibase CD3F3594C9FB5D10](https://avibase.bsc-eoc.org/species.jsp?avibaseid=CD3F3594C9FB5D10):
  `Phylloscopus occisinensis`, felosa-de-chingai, hoje tratado como subespécie
  de `P. affinis`; preservamos a classe histórica do modelo.

Os hashes dos arquivos de entrada estão em `source_sha256`. Correspondências
usam nome científico exato, sinônimo documentado com mesmo epíteto, ou nome comum
inglês exato e único (ignorando caixa, pontuação e grey/gray). Não há tradução
automática nem aproximação textual. As correspondências estão no relatório.

## Apelidos locais

Edite `name_overrides.json`, por exemplo:

```json
{"Pitangus sulphuratus": "bem-te-vi"}
```

Reinicie `coral-birds` após copiar para a Coral. O arquivo é separado do catálogo
para não perder os apelidos numa atualização. Acentos são conservados nos dados;
o publicador adapta para a fonte ASCII do OLED.

## Reconstrução

Instale `openpyxl` somente no computador de reconstrução. Baixe as fontes acima e
extraia os dois PDFs com `pdftotext -layout`. Execute:

```bash
python3 tools/build_bird_names.py \
  --model-zip BirdNET_v2.4_tflite_fp16.zip \
  --ebird-xlsx ebird-common-names.xlsx \
  --taxonomy-csv birdnet-taxonomy.csv \
  --birdnet-br birdnet-pt-br.txt \
  --aves-text aves-do-mundo-2024.txt \
  --aves-previous-text aves-do-mundo-2023.txt \
  --output sub/data
```

A Coral consulta apenas o JSON local e não precisa de internet para os nomes.
