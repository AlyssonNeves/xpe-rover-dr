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
- contratos abstratos das portas.

Recursos de autenticação, alertas operacionais e seleção global do modo de hardware
não fazem parte deste marco e terão testes adicionados nos commits correspondentes.

## Execução

```bash
pytest -q
```

Para executar todos os quality gates:

```bash
bash scripts/quality.sh
```
