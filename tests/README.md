# Testes automatizados

Este diretório reúne os testes unitários e de regressão automatizada do Rover-DR.
O conjunto foi reorganizado para acompanhar as fronteiras da arquitetura hexagonal e
pode ser executado sem hardware EV3 físico.

## Escopo neste marco

- modelos e handlers da camada de aplicação;
- validação e despacho do `CommandService`;
- repositórios de estado e adapters de saída;
- controle diferencial, odometria e navegação básica;
- roteamento REST e transporte HTTP;
- lifecycle da aplicação e infraestrutura de monitors;
- registros de comandos e reservas de motores;
- gateway controlado `ev3dev2.motor` com módulo simulado;
- autenticação dos endpoints protegidos e validação dos tokens obrigatórios;
- shutdown/restart remoto com confirmação explícita;
- formatação de erros fatais de startup para a tela do EV3;
- adapter de alerta com display, LEDs, som e reconhecimento por botão;
- contratos abstratos das portas;
- configuração global de hardware e seleção do modo de operação;
- controle manual local por joystick sobre as portas existentes, incluindo tração diferencial, motores auxiliares e parada de emergência.
- integração Linux `evdev` por adapter dedicado para descoberta e leitura do joystick;
- telas gráficas PBM para a seleção inicial dos modos no display do EV3, com validação de formato e dimensões.

## Execução

```bash
pytest -q
```

Para executar todos os quality gates:

```bash
bash scripts/quality.sh
```
