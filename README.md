#  FinançasBob - Automação Financeira com Python

> Automação inteligente que processa extratos bancários (Nubank), categoriza gastos via regras de negócio e atualiza automaticamente uma planilha de controle financeiro no Google Sheets.

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-Data-150458?style=for-the-badge&logo=pandas&logoColor=white)
![Google Sheets API](https://img.shields.io/badge/Google_Sheets-API-34A853?style=for-the-badge&logo=googlesheets&logoColor=white)

##  O Problema
Preencher planilhas financeiras manualmente é repetitivo e propenso a erros. Este projeto resolve isso automatizando o fluxo de dados do banco para o dashboard pessoal.

##  Funcionalidades
* **Leitura Automática:** Detecta e processa arquivos `.csv` do Nubank na pasta `extratos`.
* **Categorização Inteligente:** Usa palavras-chave para classificar gastos (Ex: "Uber" -> Transporte, "Smartfit" -> Saúde/Lazer).
* **Gestão de Duplicatas:** Cria um *Hash* único para cada transação, impedindo que gastos sejam lançados duas vezes.
* **Integração Visual:** Preenche as células exatas do Dashboard (Entradas, Gastos Fixos e Variáveis).
* **Logs de Auditoria:** Gera arquivos de log para rastrear cada ação do robô.

##  Como Configurar

### 1. Pré-requisitos
```bash

pip install pandas gspread oauth2client gspread-dataframe
