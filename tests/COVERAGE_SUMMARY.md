# Cobertura automatizada

O projeto utiliza cobertura de linhas e branches por meio de `coverage.py`.
Neste marco, o quality gate inicial exige cobertura global mínima de **60%**.

```bash
coverage erase
coverage run -m pytest
coverage report -m
coverage xml
```

A configuração oficial está em `.coveragerc`. O arquivo `coverage.xml` é um artefato
de execução/CI e não deve ser versionado.


Neste Commit 20 (S02.01), **67 testes** foram aprovados e a cobertura global medida foi de **70%**, mantendo o gate mínimo de 60%.
