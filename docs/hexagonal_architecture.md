# Arquitetura Hexagonal do Rover-DR

## Objetivo

O Rover-DR adota uma arquitetura hexagonal para manter regras de aplicação e serviços de domínio independentes dos mecanismos de entrada e saída. O servidor HTTP, o hardware EV3 e os repositórios de estado são detalhes de infraestrutura conectados ao núcleo por portas e adapters explícitos.

## Fluxo de entrada

```text
HTTP
  |
  v
RestApiServer              transporte HTTP e serialização JSON
  |
  v
CommandRoutes              mapeamento de URI/verbo para comandos da aplicação
  |
  v
CommandService             validação do envelope e despacho
  |
  v
DomainCommandHandler       sensor | motor | controller | rover | drive
  |
  v
Ports                      contratos de aplicação
  |
  v
Services / Output Adapters hardware, monitoração e estado
```

## Responsabilidades

### `adapters/in_rest_api_server.py`

Responsável apenas por HTTP: leitura do corpo, parsing do caminho, CORS, códigos de transporte, serialização e tratamento da conexão.

### `adapters/rest/command_routes.py`

Concentra o roteamento de endpoints. Nenhum serviço de domínio conhece URIs, métodos HTTP ou objetos `BaseHTTPRequestHandler`.

### `app/command_service.py`

Valida o envelope do comando e regras comuns de parâmetros. O despacho por domínio é realizado por um registro de handlers.

### `app/commands/domain_handlers.py`

Define handlers explícitos para Sensor, Motor, Controller, Rover e Drive. Essa camada impede que adapters de entrada selecionem diretamente implementações de serviço.

### `ports/*`

São os contratos que separam a aplicação das implementações concretas.

## Regra de dependência

As dependências devem apontar para dentro. Serviços de domínio e portas não importam o servidor REST. A camada HTTP conhece apenas modelos de aplicação e o facade de comandos.

## Compatibilidade

Esta refatoração não altera os endpoints públicos introduzidos até o Commit 14. Seu objetivo é reorganizar responsabilidades e reduzir acoplamento antes da ampliação dos testes e quality gates.
