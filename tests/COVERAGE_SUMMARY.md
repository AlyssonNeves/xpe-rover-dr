# Cobertura automatizada

O projeto utiliza cobertura de linhas e branches por meio de `coverage.py`.
O quality gate deste estágio mantém cobertura global mínima de **60%**.

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
