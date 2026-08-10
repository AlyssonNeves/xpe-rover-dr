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
