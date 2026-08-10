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
