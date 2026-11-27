# Pássaros na Coral, direção e microSD na ESP32

A Coral usa o microfone USB da **HD Pro Webcam C920**, selecionado por
`plughw:CARD=C920,DEV=0` em `sub/services/birds.json`. O BirdNET processa janelas de 3 segundos; o
limiar configurado é 0,15. É um score do modelo, não uma probabilidade calibrada
de acerto. O modelo existente roda na **CPU da Coral**, não no Edge TPU. O serviço
importa e verifica o bundle já instalado pelo projeto `Documentos/Coral`, sem
alterá-lo nem incluir seus pesos neste repositório.

Fluxo: microfone USB da webcam → Coral/BirdNET → MQTT local → ponte serial → USB/CP2102/UART
(JSON por linha) → ESP32. A ESP não executa MQTT. Quatro MAX4466 → MCP3008 → tarefa
RMS da ESP; outra tarefa grava no microSD. Apenas a tarefa de display acessa o OLED.

## Comportamento

- Detecção acima do limiar: nome na área azul e direção na faixa amarela/laranja,
  calculada sobre a mesma janela de áudio. Ambos ficam fixos até o próximo resultado.
- Sem detecção: `Ouvindo...` em azul, faixa de direção vazia.
- Ausência de novas observações: expira em até 8 segundos após o fim da janela de
  áudio usada. O atraso de processamento/envio é descontado. Não persiste detecções
  na flash nem no broker. Retentativas não renovam a validade de uma detecção antiga.
- RMS calculado como `sqrt(média(x²) - média(x)²)`, removendo o DC dos MAX4466.
  Ganha o maior canal; piso de 3 unidades ADC e vantagem mínima de 10% sobre o
  segundo. A comparação usa a média temporal de RMS² dos blocos que sobrepõem
  a janela classificada (seguida da raiz quadrada). Empate, sinal fraco, canal inválido
  ou histórico incompleto: `Indef.`.
- CH0=Norte, CH1=Leste, CH2=Sul, CH3=Oeste é **uma atribuição provisória**. Não é bússola
  e não há orientação geográfica automática. Ajuste conforme a montagem.
- Janela de 512 leituras por canal, alvo de intervalo de 250 µs, com pausas para
  outras tarefas. `window_us` informa a duração real; não é captura simultânea ou
  localização por tempo de chegada. O isolamento acústico e ganhos iguais são essenciais.
- **Buzzer desativado** (`BUZZER_ENABLED=false`); o firmware não configura nem aciona
  GPIO33. Não reative antes de conferir o módulo e sua polaridade. O código opcional
  prevê bip de 80 ms ao entrar em detecção ou mudar de espécie, com intervalo mínimo de
  10 s. Durante o bip e 500 ms após ele não se estima direção. Os campos `muted` e
  `direction_valid` identificam esse período. O microfone da Coral continua capturando.
- Comandos manuais continuam funcionando, mas o classificador atualiza a tela na
  próxima observação. Pare o serviço para manter uma mensagem manual.

## Sincronização da identificação com a direção (firmware 1.5)

A classificação continua a cada **3 segundos**, sobre janelas de 3 segundos.
A Coral calcula o fim da janela a partir da idade de captura informada pelo runtime,
descontando espera e inferência. Envia `window_start_ms` e `window_end_ms` absolutos;
a ponte preserva esses valores em atrasos e retentativas, junto com um `epoch_ms`
novo no instante de envio serial.

A ESP mantém 160 blocos RMS em memória (aproximadamente 23 segundos), usando seu
relógio monotônico. Ao receber a identificação, converte a janela para esse relógio
e combina a energia dos blocos históricos, ponderando a duração de sobreposição.
O resultado é congelado junto ao nome: sons posteriores não mudam a direção da
identificação anterior. Uma repetição da mesma janela mantém o resultado original.

`direction_sync=matched` significa cobertura de pelo menos 95% da janela;
a direção ainda pode ser `Indef.` por empate ou sinal inadequado. Após reinício,
lacunas ou janela antiga demais, retorna `history_incomplete`; comandos antigos sem
horários retornam `missing_window`. Nunca substitui histórico ausente pela direção
atual. O firmware 1.5 deve ser instalado junto com o publicador atualizado.

É alinhamento por software, não sincronização de amostras: permanecem a latência
de entrega do áudio USB/ALSA, o transporte serial e a resolução dos blocos RMS
(normalmente cerca de 144 ms, podendo aumentar sob carga). Se a fonte mudar de posição dentro dos 3 segundos, a direção
representa a maior energia no trecho inteiro; forças semelhantes resultam em `Indef.`.

## Pinagem do esquema fornecido

| Módulo | Sinais |
| --- | --- |
| MCP3008, VSPI | SCK 18, MISO 19, MOSI 23, CS 4; microfones CH0–CH3 |
| microSD HW-125, HSPI | SCK 14, MISO 27, MOSI **26**, CS **13** |
| Buzzer ativo **com driver** | IN/S GPIO33; desativado, polaridade a conferir |
| OLED e RTC, I²C | SDA21, SCL22 |

MCP3008 e microfones a 3,3 V. O leitor HW-125 do esquema recebe 5 V e usa sinais a
3,3 V. O firmware não formata o cartão. As duas interfaces SPI operam inicialmente
a 1 MHz. Referências: [MCP3008, Microchip](https://ww1.microchip.com/downloads/aemDocuments/documents/MSLD/ProductDocuments/DataSheets/MCP3004-MCP3008-Data-Sheet-DS20001295.pdf)
e [SD, Espressif](https://github.com/espressif/arduino-esp32/blob/2.0.17/libraries/SD/src/SD.h).

Edite `sub/firmware/coral_display/bird_config.h` para trocar direções, ganhos,
piso de RMS, margem de decisão ou pinagem. Recompile e grave a ESP após mudar esse
arquivo. Primeiro confirme CH0–CH3 falando próximo de cada microfone e observando
os quatro RMS; depois ajuste os nomes. Com a mesma fonte e distância em cada canal,
ajuste os ganhos para respostas semelhantes. Não atribuímos direções intermediárias
sem calibração e medição apropriadas.

## Registros: só dados, a cada 0,5 segundo

O cartão recebe `/birds-AAAA-MM-DD.jsonl`, uma linha JSON por amostragem do estado,
inclusive quando não há pássaro. Não guarda áudio. Campos:

- `timestamp_utc`, `epoch_ms`: hora enviada pela Coral e avançada por relógio
  monotônico da ESP entre mensagens; UTC. Sem sincronização inicial, timestamp vazio,
  epoch 0 e arquivo `/birds-unsynced.jsonl`.
- `active`, `name`, `scientific_name`, `score`: classificação válida no instante.
- `direction`, `direction_valid`: direção congelada da janela classificada.
- `window_start_ms`, `window_end_ms`, `direction_sync`, `direction_coverage`,
  `window_rms[4]`: intervalo do áudio e evidência histórica usada para a direção.
- `rms[4]`, `mean[4]`, `muted`, `window_us`: diagnóstico ao vivo dos microfones;
  esses valores não substituem `window_rms` na direção apresentada.
- `session`: identificador aleatório por boot; `uptime_ms`: momento da escrita.

Após fechar e reabrir a linha para conferência, a ESP emite `bird_record` no tópico
`coral/esp32/events`, com `saved` e `path`. `saved:false` indica falha real: cartão
ausente/cheio/incompatível ou erro de escrita. `bird.records_saved/records_lost`
no ACK de status acumulam resultados desde o boot. A fila tem 8 registros; se ficar
cheia, o contador de perdas aumenta. Não há recuperação automática de registros
perdidos nem exclusão automática de arquivos antigos. O evento MQTT é transitório;
o registro durável é o arquivo no cartão. Remova o cartão com a montagem desligada.

A cadência é aproximadamente 0,5 s, com pequeno atraso de aquisição/agendamento; não
é temporização de laboratório. Uma detecção menor que esse intervalo pode não
coincidir com uma linha. O cartão salva o estado corrente, não cada evento individual.
Nome, direção e `window_rms` se referem à última janela classificada, repetida nos
registros de 0,5 s até chegar o próximo resultado. Não são novas inferências a cada
registro. `epoch_ms` é o horário do registro; os campos `window_*_ms` são os do áudio.

O horário depende do relógio do Linux da Coral. Mantenha a Coral com acesso a NTP;
um RTC sem bateria não conserva a hora durante falta de energia. Não se deve
interpretar a presença de timestamp como prova de sincronização UTC por NTP.

## Instalação e início automático

Pré-requisitos: broker/ponte deste repositório instalados, firmware 1.5 gravado,
bundle BirdNET funcionando em `/home/mendel/bird_recognition/current`, ALSA/arecord,
NumPy e TFLite Runtime já instalados pelo projeto `Documentos/Coral`. O modelo tem
licença própria; consulte `BIRDNET_LICENSE.txt` no bundle. Não copie modelos para o Git.

Na Coral, na raiz do repositório:

```sh
python3 -m pip install -r requirements.txt
sudo cp sub/services/coral-birds.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now coral-birds.service
journalctl -u coral-birds.service -f
```

Para ajustar o limiar, edite `sub/services/birds.json` (`threshold`: 0 a 1), depois:

```sh
sudo systemctl restart coral-birds.service
```

`every` é a cadência da classificação, `lifetime` o prazo máximo da observação.
O registro no cartão permanece a cada 0,5 segundo independentemente desses valores.
Os dispositivos são identificados pelo nome ALSA, sem depender do número da
placa USB. O serviço prefere microfones externos no boot e verifica conexões a
cada 2 segundos. Se um externo chegar enquanto o nativo estiver em uso, troca
automaticamente; se o externo sair, usa outra entrada disponível, preferindo
outros externos. Entre externos, mantém o atual; no boot, prefere a seleção
salva ou `device` da configuração quando disponível.
Ao selecionar o nativo, `configure-microphone.sh` ajusta o RT5645.
Uma entrada com falha de captura fica 30 segundos sem nova tentativa, permitindo
usar outra. Três janelas consecutivas sem sinal útil também provocam essa troca;
não são tratadas como silêncio
normal. O serviço abre o microfone ao iniciar, sem comando de publicação manual. Se a ESP
estiver ausente, continua classificando e tenta enviar as próximas observações.
Não execute outro gravador simultaneamente no mesmo microfone.

Acompanhar registros pelo PC, na raiz do repositório:

```sh
python3 -m pub.pc --events --count 3 --timeout 30
```

Na Coral: `python3 -m pub.events`. `python3 -m pub --status` lê o último ACK retido,
não uma consulta instantânea aos sensores. Cada observação da Coral produz um novo
ACK; quando o classificador está parado, use a serial diretamente com a ponte parada
para obter estado atual. Para usar o display manualmente:

```sh
sudo systemctl stop coral-birds.service
python3 -m pub --blue "Coral" --yellow "Pronta"
# Retomar:
sudo systemctl start coral-birds.service
```

## Testes

```sh
python3 -m unittest discover -s tests -v
g++ -std=c++11 -Wall -Wextra -fsanitize=address,undefined tests/test_rms.cpp -o /tmp/test-rms
/tmp/test-rms
bash sub/build.sh
```

Para o teste físico, pare `coral-birds` e `coral-display-subscriber`; rode
`PYTHONPATH=. python3 tests/check_birds_hardware.py` na Coral,
e reinicie os dois serviços ao terminar. O teste envia `TESTE`, mantém o buzzer desativado, valida
os quatro canais, exige escrita e releitura no cartão e verifica que a habilitação
expira sozinha. É uma detecção sintética, não um ensaio de reconhecimento acústico.
A direção física exige ensaio na montagem.

## Botão para escolher o microfone (firmware 1.6)

Botão normalmente aberto entre **GPIO32 e GND**, com `INPUT_PULLUP` e debounce
40 ms. Cada pressão completa emite um evento `microphone_next` pela USB serial.
A ponte publica em `coral/esp32/events`; o serviço `sub.birds` fecha a captura
anterior e alterna os dispositivos de entrada realmente presentes no ALSA.
O conector I2S `Header` sem microfone é excluído. Segurar o botão não repete.

O display apresenta o nome do microfone e `Selecionando...`; após receber áudio,
mostra `Microfone ativo` por **4 segundos**. A sobreposição ocupa as duas cores,
enquanto as classificações continuam atualizando o estado de fundo. Ao terminar,
volta à ave/direção atual. Clicar novamente reinicia o aviso e troca de entrada.
Com só um microfone disponível, mostra o mesmo, sem reiniciar a captura.

A seleção confirmada fica em `~/.config/coral-birds/microphone.json`. No boot,
um externo tem prioridade mesmo se a seleção salva for o nativo. Uma escolha
manual pelo botão permanece até essa entrada ser removida ou um novo externo
ser conectado; nesse momento a preferência automática volta a valer. A primeira inferência após troca necessita
uma nova janela de 3 s. Resultados da captura anterior são descartados; a direção
continua vinculada ao horário da janela que foi classificada.

Estado consultável em `coral/birds/microphone` (MQTT retido): `device`, `label`,
`available`, `status`, `error`. A mensagem de tela usa o tópico transitório
`coral/display/notice`, separado das mensagens normais para não substituí-las.

Os [nomes populares](sub/data/README.md) são aplicados na Coral antes da publicação,
sem modificar o modelo verificado. O limiar permanece **0.15**, a janela **3 s**
e o buzzer permanece desabilitado.

### Validação em 16/11/2026

- 33 testes Python passaram no computador e na Coral (Python 3.7).
- Debounce passou em C++ com AddressSanitizer/UndefinedBehaviorSanitizer na Coral.
- Firmware 1.6 compilado para ESP32 Arduino 2.0.17: 392.197 bytes.
- Catálogo conferido contra o checksum e as 6.522 chaves dos rótulos instalados.
- Serviço atualizado e ativo, capturando áudio real do microfone interno.
- Clique simulado no broker real gerou o aviso correto de 4 s; reentrega do
  mesmo evento não gerou outro aviso.
- Após reconectar os periféricos, firmware **1.6 gravado e hash verificado**.
  A transferência a 460800 baud travou na leitura, antes de qualquer gravação;
  backup completo e gravação concluídos a 115200 baud.
- Sobreposição testada na ESP real: permanece durante atualizações do conteúdo
  de fundo e expira em 4 segundos, restaurando a tela mais recente.
- Troca real **Coral → C920 → Coral → C920** aprovada por eventos de teste no
  MQTT; a cada seleção há confirmação de áudio e apenas um processo `arecord`.
  A C920 foi restaurada automaticamente após reiniciar o serviço.
- Teste de janela RMS aprovado no firmware 1.6: cobertura 99,4%, direção
  congelada na janela correta, expiração e buzzer desligado verificados.
- No teste de janela houve 7 eventos de registro, mas 0 gravações confirmadas
  no SD. O estado do cartão segue intermitente; essa validação não comprova
  armazenamento confiável no cartão.
- Clique físico: aguardando acionamento pelo usuário; o teste MQTT não o substitui.

Backup completo pré-1.6 (4 MiB), na pasta `backups/` do projeto no PC e na Coral:
`before-1.6-20261116-034931.bin`.
SHA-256: `dd174f6b0cae72c523f867962dec8be5bfb77a7e0dcfba7f0fbbb46c75bc2fa1`.

Backup anterior na Coral: `/home/mendel/coral-before-microphones-20261116-032941.tar.gz`.
Nada foi publicado no GitHub.


### Preferência automática por microfones externos — 16/11/2026

- 38 testes Python aprovados no PC e na Coral, incluindo prioridade no boot,
  chegada e remoção de USB, escolha manual e espera após falha de captura.
- Verificado com áudio real: início do serviço sem C920 → microfone nativo;
  reativação do áudio USB → C920; remoção → nativo; reconexão → C920.
  A remoção/conexão foi simulada desassociando e reassociando as duas interfaces
  de áudio USB da webcam ao driver, sem retirar fisicamente o cabo.
- A primeira captura após reativar o driver falhou transitoriamente. O serviço
  usou o nativo durante a espera de 30 s e retomou a C920 automaticamente.
  Na última etapa, a confirmação ultrapassou o limite de 40 s do script de teste;
  os logs posteriores e uma verificação separada confirmaram áudio real da C920,
  somente um processo de captura e os dois serviços ativos.
- Atualização instalada na Coral; firmware da ESP não alterado nesta etapa.


### Confiança no display (firmware 1.7)

A área azul reserva 32 pixels para o nome da ave e 16 para a confiança do modelo,
centralizada como `56%` (score 0,556 arredondado). A faixa laranja continua mostrando
a direção da mesma janela de áudio. Nomes longos mantêm quebra de linha e paginação;
a porcentagem permanece visível em todas as páginas. A porcentagem acompanha cada
classificação e desaparece quando não há detecção ou quando a observação expira.
É o score de confiança do BirdNET, não uma medida de precisão validada.
O ACK/status inclui `bird_confidence`; `bird.score` mantém o valor original.

Validado na ESP em 16/11/2026: gravação com hash verificado; testes de 0%, 15%,
50%, 56% e 100%, paginação com porcentagem fixa, ausência de detecção e expiração
aprovados. Teste da direção na mesma janela aprovado (cobertura 99,39%). Layout
C++ aprovado com AddressSanitizer/UndefinedBehaviorSanitizer; 38 testes Python
aprovados. O cartão continuou com a falha intermitente já registrada (0 de 7
registros salvos neste teste).
