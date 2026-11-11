# Publicadores

Todos os exemplos partem da raiz do repositório.

## MQTT na Coral ou no PC

```sh
python3 -m pip install -r pub/requirements.txt
python3 -m pub "Minha mensagem"
python3 -m pub --host 127.0.0.1 --port 1883 "Minha mensagem"
```

API Python:

```python
from pub.mqtt import publish
result = publish("Coral pronta")
print(result["ok"])
```

O broker padrão é `127.0.0.1:1883`, ou o host definido por `CORAL_MQTT_HOST`.
`--status` lê a última confirmação MQTT retida, sem consultar o RTC em tempo real.
`--clock` e `--clear` também publicam comandos pelo broker.

## PC via SSH

Não requer pyserial nem Paho no PC:

```sh
python3 -m pub.pc "Mensagem do PC" --host mendel@ENDERECO_DA_CORAL
python3 -m pub.pc "Outra mensagem" --host coral-dev-board --remote-dir /home/mendel/coral-esp32-display
```

```python
from pub.pc import publish
publish("Mensagem do computador", host="mendel@ENDERECO_DA_CORAL")
```

A autenticação SSH deve funcionar sem interação. `CORAL_SSH_HOST` e `CORAL_REMOTE_DIR`
configuram os padrões. A mensagem viaja por stdin, sem ser inserida no comando do shell.
O código deste repositório deve existir na Coral.

Outra opção é encaminhar a porta e usar o publicador MQTT local:

```sh
ssh -N -L 18883:127.0.0.1:1883 mendel@ENDERECO_DA_CORAL
# Em outro terminal:
python3 -m pub --host 127.0.0.1 --port 18883 "Mensagem pelo tunel"
```

## Protocolo MQTT

| Item | Valor |
| --- | --- |
| Entrada | `coral/display/text` |
| Confirmação/estado | `coral/display/state` |
| QoS do publicador fornecido | 1 |
| Retenção | Ativada, preserva o último estado desejado |

O assinante aceita texto UTF-8 simples ou um envelope JSON:

```json
{"id":"pedido-1","cmd":"text","text":"Coral"}
```

Também aceita `cmd: "clock"` e `cmd: "clear"`. IDs de até 64 caracteres. O estado inclui
`id`, `ok`, `online` e dados do ESP32. Erros incluem `error`. `online: true` sozinho não
confirma o OLED; confira `ok` e o ID.

Integração direta com Paho:

```python
from paho.mqtt.publish import single
single("coral/display/text", "Ola, Coral", hostname="127.0.0.1", qos=1, retain=True)
```

Esse exemplo confirma entrega ao broker. `pub.mqtt.publish` aguarda também o ESP32.
Se outro publicador substituir uma mensagem pendente, a confirmação dela pode não chegar.
Publique sequencialmente quando precisar confirmar cada atualização.
