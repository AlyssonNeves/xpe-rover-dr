# Cobertura automatizada

O projeto utiliza cobertura de linhas e branches por meio de `coverage.py`.
O quality gate atual mantém cobertura global mínima de **65%**. Os marcos anteriores preservam abaixo os valores históricos vigentes em cada estágio.

```bash
coverage erase
coverage run -m pytest
coverage report -m
coverage xml
```

A configuração oficial está em `.coveragerc`. O arquivo `coverage.xml` é um artefato
de execução/CI e não deve ser versionado.

## S02.03

O marco S02.03 acrescenta a validação dos assets gráficos PBM e do carregamento das
telas de seleção de modo do EV3. A suíte completa possui **84 testes aprovados** e cobertura global de **71%**,
acima do gate mínimo de 60%.

## S02.05

O marco S02.05 separa explicitamente os parâmetros **Command** e **Control**, aplica
`Control = None` quando o comando é `REMOTE` e valida a navegação por linhas na tela
gráfica do EV3. A suíte completa possui **100 testes aprovados** e cobertura global de
**72%**, acima do gate mínimo de 60%.

## S02.07

O marco S02.07 acrescenta o fail-safe de desconexão do joystick Bluetooth: erros
do descritor/evdev interrompem imediatamente o movimento, invalidam a sessão
manual e exigem neutralidade dos eixos antes de uma retomada explícita. A suíte
completa possui **121 testes aprovados** e cobertura global de **73%**, acima do
gate mínimo de 60%.

## S02.08 - Fronteiras arquiteturais do controle manual

- Contratos explícitos: `JoystickPort`, `ManualDrivePort`, `MotorHardwarePort` e `MotorStatePublisherPort`.
- Publicação de estado do controle direto desacoplada do repositório por `MotorStateStorePublisherAdapter`.
- Testes AST impedem dependências do núcleo manual em adaptadores, `MotorMonitor` e `MotorStateStore`.

## S02.09 - Runtime LOCAL + MANUAL dedicado

- Grafo `LOCAL + MANUAL` sem `SensorMonitor`, `MotorMonitor`, `ControllerMonitor`, filas ou `Ev3Dev2MotorGateway`.
- `EvdevJoystickAdapter` montado automaticamente em hardware real.
- Consultas REST preservadas por adaptadores read-only e snapshots publicados pelo controle manual.
- Escritas REST de motor/drive bloqueadas enquanto o controle manual possui o hardware.
- A suíte completa possui **147 testes aprovados**.

## S02.10 - Reforço da arquitetura hexagonal

- Serviços de aplicação movidos para `app/services/` e infraestrutura técnica segregada em `infrastructure/`.
- Composição concreta concentrada em `bootstrap/rover_assembly.py`; `main.py` reduzido ao entry point do processo.
- Contratos de motor e sensor divididos em portas focadas, mantendo agregados somente para compatibilidade incremental.
- `MotorMonitor` passa a delegar acesso aos drivers a um repositório compartilhado e coleta de snapshots a um componente dedicado.
- Handlers de domínio e rotas REST foram decompostos em módulos explícitos, com tabela declarativa de rotas.
- Gates automatizados verificam direção das dependências, ausência do pacote legado `services/` e compatibilidade sintática com Python 3.5.
- A suíte completa possui **160 testes aprovados**, com **74% de cobertura combinada de linhas e branches**.
- A partir deste marco, o quality gate de cobertura global passa a ser **65%**.

## S02.11 - Calibração dos motores Mecanum

- Configuração explícita dos quatro motores de tração Mecanum: `LLM`, `LMM`, `RLM` e `RMM`.
- Fatores independentes de calibração por roda, inicialmente neutros (`1.0`) para não antecipar as correções de polaridade e RPM.
- `ManualDrivePort` passa a expor `apply_mecanum_setpoint()` para escrita síncrona dos quatro motores.
- `ManualDriveService` valida quatro códigos distintos, aplica a calibração individual e realiza rollback dos quatro motores quando qualquer comando falha.
- A suíte completa possui **166 testes aprovados**, com **74% de cobertura combinada de linhas e branches**.

## S02.12 - Correção da polaridade e cinemática

- Polaridade física global validada e aplicada exclusivamente pela fábrica de drivers EV3.
- Fatores Mecanum passam a aceitar sinais, mantendo a inversão específica do drivetrain separada da polaridade global.
- Fatores direcionais deste marco: dianteiros `-1.0` e traseiros `+1.0`; compensação de magnitude por RPM permanece para S02.23.
- Cinemática lógica Mecanum normalizada cobre avanço, ré, strafe, diagonais e rotação sem embutir polaridade física.
- Convenção Linux `evdev` de Y negativo para cima é convertida para avanço lógico positivo.
- A suíte completa possui **171 testes aprovados**, com **74% de cobertura combinada de linhas e branches**.

## S02.13 - Telas e cache PBM

- Os assets executáveis do display EV3 passam a residir em `assets/screens/cache/` como PBMs 1-bit de 178 x 128 pixels.
- O pacote contém **15 telas PBM** validadas, incluindo os fundos reservados para inicialização, Bluetooth, Front/Drive/Centric e status de motores.
- `infrastructure/ev3/screen_image.py` centraliza carregamento, validação, cache em memória e invalidação quando o arquivo de origem é alterado.
- `warm_monochrome_screen_cache()` pré-carrega os PBMs no startup quando o hardware EV3 está habilitado; falhas são reportadas e a tela afetada pode tentar novo carregamento quando utilizada.
- Não há conversão TIFF/SVG no runtime do Rover; os adaptadores de Command & Control e General Status leem diretamente do cache deployável.
- A suíte completa possui **179 testes aprovados**, com **74% de cobertura combinada de linhas e branches**.


## S02.14 - Configuração Robot-Centric

- Runtime `LOCAL + MANUAL` configurado para `MECANUM + CHASSIS` (Robot-Centric).
- Stick esquerdo X/Y controla strafe/avanço e stick direito X controla rotação.
- `strafe_compensation = 1.1` é aplicado antes da normalização Mecanum comum.
- D-pad não comanda `LMM`/`RMM` enquanto os quatro motores pertencem à tração Mecanum.
- A barreira pós-desconexão passa a exigir neutralidade de X, Y e RX em Mecanum.
- A suíte completa possui **187 testes aprovados**, com **75% de cobertura combinada de linhas e branches**.


## S02.15 - Perfis de movimento

- Perfis suportados: `direct`, `ramp-up`, `ramp-down` e `ramp-up-down`.
- `direct` limpa as rampas nativas; os demais perfis ativam `ramp_up_sp` e/ou `ramp_down_sp` conforme a configuração global.
- `MotorCommandExecutor` centraliza o mapeamento de perfil e a emissão do comando ao repositório de drivers.
- Comandos REST individuais, sincronizados e de navegação validam e propagam `profile`.
- A suíte completa possui **194 testes aprovados**, com **75% de cobertura combinada de linhas e branches**.

## S02.16 - Fluxo canônico de seleção dos modos do Rover

- `RoverOperationMode` centraliza `command`, `control`, `front`, `drive` e `centric`.
- `REMOTE` torna `control/front/drive/centric` não aplicáveis; `DIFFERENTIAL` torna `centric` não aplicável.
- Novo `LocalDriveSetupSelectorPort` e adaptador EV3 para `Front/Drive/Centric`, reutilizando as seis telas PBM do S02.13.
- O composition root executa a seleção local somente para `LOCAL` e passa `DIFFERENTIAL`/`MECANUM` e `CHASSIS` ao pipeline manual conforme a escolha do operador.
- `MECANUM + FIELD` é reconhecido pelo modelo, mas permanece bloqueado até existir fonte de heading no S02.20/S02.21.
- `/api/state` expõe o snapshot canônico completo do modo operacional.
- A suíte completa possui **200 testes aprovados**, com **81% de cobertura combinada de linhas e branches**.

## S02.17 - Deadzone e resposta exponencial do joystick

- `axis_center`, `axis_deadzone`, `axis_max` e `axis_response_intensity` passam a compor a configuração explícita do controle manual.
- Valores dentro da deadzone são neutros e o curso restante é renormalizado integralmente para `[-1, +1]`.
- A resposta exponencial é aplicada após a remoção da deadzone e preserva sinal e escala máxima.
- Configurações que eliminem um lado útil do eixo ou usem intensidade não positiva são rejeitadas.
- O composition root injeta os parâmetros de shaping no `JoystickControlService`.
- A suíte completa possui **209 testes aprovados**, com **73% de cobertura combinada de linhas e branches**.

## S02.18 - Orientação NOSE/TAIL

- `JoystickControlService` recebe explicitamente o `front` canônico selecionado no startup.
- `NOSE` mantém os setpoints diferenciais e Mecanum no referencial original.
- `TAIL` transforma Differential como `(-right, -left)`, invertendo translação e trocando os lados lógicos.
- Em Mecanum, `TAIL` aplica `(-RR, -FR, -RL, -FL)`, equivalente a rotacionar o referencial translacional do operador em 180 graus sem inverter o sentido de rotação solicitado.
- A transformação de orientação permanece separada de polaridade física, fatores Mecanum e futura compensação de RPM.
- A suíte completa possui **214 testes aprovados**, com **74% de cobertura combinada de linhas e branches**.


## S02.19 - Conexão e reconexão automática do joystick Bluetooth

- `bluetoothctl connect <MAC>` é acionado somente quando o joystick ainda não está disponível em `evdev`.
- Falhas de conexão e perdas durante leitura mantêm o worker ativo em ciclo automático de retry.
- Cada tentativa começa com parada síncrona dos motores e conexões recuperadas continuam protegidas pela neutral-safety barrier.
- A tela `Screen 03 - Bluetooth Error.pbm` apresenta o estado de falha até a recuperação.
- Configuração explícita: `device_address`, `auto_connect`, `connection_retry_seconds`, `connection_timeout_seconds` e `discovery_poll_seconds`.
- A suíte completa possui **226 testes aprovados**.

## S02.20 - Pipeline dedicado para controle FIELD-centric

- Novo `HeadingQueryPort` read-only para o caminho de baixa latência.
- `HeadingStateStore` mantém o último heading publicado em cache sem acesso físico ao sensor.
- `HeadingStateQueryAdapter` rejeita amostras ausentes ou mais antigas que `field_heading.max_age_seconds`.
- `JoystickControlService` transforma X/Y do campo para o chassi antes da cinemática Mecanum.
- Heading indisponível interrompe a tração FIELD e rearma a barreira de neutralidade.
- `CHASSIS` permanece independente da consulta de heading.
- O composition root aceita uma fonte de heading em cache injetada; a criação do produtor físico fica para S02.21.
- A suíte completa possui **235 testes aprovados**, com **74% de cobertura combinada de linhas e branches**.

## S02.21 - Integração do giroscópio

- Novo `HeadingSensorPort` para a fronteira física do heading.
- `Ev3GyroSensorAdapter` configura `in3` como `ev3-uart`, usa `GYRO-ANG` e tenta detectar o sensor durante o timeout configurado.
- Calibração de montagem aplicada na fronteira EV3 por `angle_sign = -1.0` e `angle_offset_deg = 0.0`.
- `GyroHeadingMonitor` publica apenas o heading do sensor configurado no `HeadingStateStore` e marca amostras indisponíveis em falhas de leitura.
- O monitor dedicado é montado somente em `LOCAL + MANUAL + MECANUM + FIELD`; CHASSIS e Differential continuam sem monitor de giroscópio.
- Consultas REST do sensor `GYR` usam o mesmo heading em cache e nunca fazem I/O físico na requisição.
- A suíte completa possui **247 testes aprovados**, com **74% de cobertura combinada de linhas e branches**.
