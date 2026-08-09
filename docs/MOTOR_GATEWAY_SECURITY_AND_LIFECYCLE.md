# EV3Dev2 Motor Gateway — Segurança e ciclo de vida

## Escopo

O gateway expõe somente o domínio de motores necessário ao Rover-DR. A superfície pública é baseada em listas explícitas de classes, métodos e propriedades permitidos; membros privados, classes fora do escopo e escrita direta em propriedades perigosas são rejeitados.

A partir deste marco, todo endpoint `/api/ev3dev2/motor/...` exige o token dedicado definido em `ROVER_HARDWARE_API_TOKEN`. O cliente deve enviá-lo em `X-Rover-Hardware-Token` ou como `Authorization: Bearer <token>`. A validação ocorre no adapter HTTP antes que qualquer método do gateway seja chamado. O token não possui valor padrão e não deve ser armazenado no repositório.

## Limite de hardware

Objetos criados pelo gateway só podem utilizar portas de motores já cadastradas em `config/rover_config.json`. A vinculação real do objeto é conferida após a criação para impedir acesso a portas não configuradas.

Operações nativas passam pelo `MotorPort`. Antes de uma operação protegida, os motores envolvidos são reservados e comandos pendentes são cancelados. Enquanto houver reserva ativa, novos comandos Rover para o mesmo motor são rejeitados.

## Classificação de operações

As chamadas são classificadas como:

- `READ_ONLY`;
- `IMMEDIATE_CONFIGURATION`;
- `BOUNDED_BLOCKING`;
- `BOUNDED_NON_BLOCKING`;
- `CONTINUOUS`;
- `BACKGROUND_SERVICE`;
- `STOP`.

Operações contínuas exigem `rover_watchdog_ms`. Operações não bloqueantes e métodos `wait*` exigem `rover_timeout_ms` quando aplicável.

## Ciclo de vida

Objetos recebem identificadores próprios e possuem TTL. O serviço de lifecycle remove objetos inativos e encerra operações que excedem watchdog ou deadline. A remoção de um objeto e o encerramento da aplicação realizam parada física best-effort antes de liberar as reservas.

`GET /api/ev3dev2/motor/operations` fornece snapshots das operações gerenciadas pelo gateway.
