# Assinante, serial e firmware

`subscriber.py` roda na Coral e mantém a conexão serial. O firmware em
`firmware/coral_display/` interpreta os comandos e desenha a mensagem no OLED.

## Preparar a Coral

Os modelos de serviço pressupõem usuário `mendel` e repositório em
`/home/mendel/coral-esp32-display`. Ajuste os caminhos se usar outra localização.

Na raiz do repositório, instale as dependências no Python que executará o serviço:

```sh
python3 -m pip install --user -r requirements.txt
sudo usermod -aG dialout mendel
mkdir -p mqtt-state
```

Uma nova sessão aplica a participação no grupo `dialout`. O broker Mosquitto precisa
estar instalado. O modelo usa `/usr/sbin/mosquitto`; se foi compilado separadamente,
ajuste `ExecStart`. Não execute dois brokers na porta 1883. Para usar um broker existente,
configure os tópicos/retenção nele e ajuste a dependência no serviço do assinante.

Revise os três arquivos de `sub/services/` antes de instalar:

```sh
sudo install -m 644 sub/services/coral-display-broker.service sub/services/coral-display-subscriber.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now coral-display-broker coral-display-subscriber
```

O broker do exemplo escuta só em `127.0.0.1`. Acesso remoto pelo SSH. Dados retidos são
salvos a cada 10 segundos e no encerramento normal; queda abrupta de energia pode perder
a última publicação.

Para executar manualmente, com broker pronto e sem outro assinante ativo:

```sh
python3 -m sub
```

`CORAL_DISPLAY_PORT` seleciona a serial. O padrão procura um único CP210 em
`/dev/serial/by-id/`, com fallback para `/dev/ttyUSB0`. `CORAL_MQTT_HOST` seleciona o host
do broker na porta 1883. O assinante reconecta e reaplica a mensagem desejada. Payloads
inválidos são recusados; se um cliente retiver um inválido, publique um válido por cima.

## Compilar e gravar

Com Arduino CLI instalado:

```sh
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@2.0.17 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli lib install 'Adafruit SSD1306@2.5.13' 'Adafruit GFX Library@1.13.0' 'Adafruit BusIO@1.17.4' 'ArduinoJson@6.21.5'
bash sub/build.sh
```

Binários em `sub/build/`. Variáveis `ARDUINO_CLI`, `ARDUINO_CLI_CONFIG` e
`ARDUINO_BUILD_PATH` permitem usar ferramentas em instalação isolada.

Faça backup da flash antes de gravar e pare qualquer leitor da serial. A gravação
substitui o firmware instalado. Com o ESP32 ligado à máquina do Arduino CLI:

```sh
arduino-cli upload --fqbn esp32:esp32:esp32 --port /dev/ttyUSB0 --input-dir sub/build sub/firmware/coral_display
```

Se o ESP32 estiver ligado à Coral, copie os binários e use o uploader compatível
instalado nela. O backup original da placa de desenvolvimento não é distribuído.

## Hardware e apresentação

- SSD1306 128 × 64; SDA=21, SCL=22; endereço 0x3C ou 0x3D.
- DS3231 opcional em 0x68: apenas leitura, sem ajuste de data/hora.
- Rotação 180° em `oled.setRotation(2)`; ajuste para outra montagem.
- `text_layout.h` calcula palavras, fonte, páginas e centralização por área: azul
  em y=0..47 e amarelo em y=48..63, na orientação atual. Essas cores pertencem ao
  painel físico. Para outra montagem, ajuste `BLUE_TOP`, `BLUE_HEIGHT`, `YELLOW_TOP`,
  `YELLOW_HEIGHT` e a rotação. Texto simples usa o azul; o relógio usa data/hora no
  azul e temperatura no amarelo. Firmware 1.2 acrescenta o comando `regions`.
- Cada região tem seu próprio índice de mensagem e página. O intervalo é de 3 s;
  uma mensagem curta única fica fixa. Listas têm até 8 itens por região, com limite
  total de 1024 caracteres. O comando serial recebe `blue` e `yellow` como arrays.
  API: `display.show_regions("Coral", "Pronta", remember=False)`.
- USB serial 115200 baud, 8N1, JSON por linha, até 2304 bytes por quadro.
- O assinante usa `remember=False`; persistência no broker, sem gravar cada texto na flash.

## Manutenção e teste real

```sh
systemctl status coral-display-broker coral-display-subscriber
journalctl -u coral-display-subscriber -f
```

Antes de usar a serial diretamente:

```sh
sudo systemctl stop coral-display-subscriber
python3 -m sub.serial_display "Teste direto"
# Altera a tela e termina com Coral persistido:
python3 -m sub.test_hardware
sudo systemctl start coral-display-subscriber
```

O teste real exige OLED e RTC. O ACK valida o protocolo e resposta I²C; orientação e
aparência físicas precisam de confirmação visual.

Referências: [Mosquitto](https://mosquitto.org/download/),
[Paho MQTT](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html),
[SSD1306](https://github.com/adafruit/Adafruit_SSD1306) e
[esptool](https://docs.espressif.com/projects/esptool/en/latest/esp32/esptool/basic-commands.html).
