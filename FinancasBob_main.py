"""
Sistema de Automacao Financeira - Integracao com Google Sheets
Versao: 2.4 - Public Release
Autor: Samuel Pires

Funcionalidades:
- Leitura de extratos bancarios (CSV)
- Categorizacao automatica via IA (Regras de Negocio)
- Deteccao de duplicatas (Hash MD5)
- Integracao via API Google Sheets
- Sistema de Logs e Auditoria
"""

import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import get_as_dataframe
from datetime import datetime
import os
import hashlib
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler

# ==============================================================================
# CONFIGURACAO DE LOGGING
# ==============================================================================
def configurar_logging():
    """Configura logging para arquivo e console"""
    os.makedirs('logs', exist_ok=True)
    log_filename = f'logs/financas_automacao_{datetime.now().strftime("%Y%m")}.log'
    
    logger = logging.getLogger('FinancasBob')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    
    formato = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler = RotatingFileHandler(log_filename, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formato)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formato)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = configurar_logging()

# ==============================================================================
# CONFIGURACOES GLOBAIS
# ==============================================================================
class Config:
    # ARQUIVOS DE CONFIGURACAO
    # ATENCAO: O arquivo .json de credenciais NAO deve ser subido para o GitHub
    CREDENCIAIS_JSON = 'credenciais.json' 
    
    # ID DA PLANILHA (Substitua pelo ID da sua planilha Google)
    # Voce encontra o ID na URL: docs.google.com/spreadsheets/d/SEU_ID_AQUI/edit
    PLANILHA_ID = 'INSIRA_SEU_ID_DA_PLANILHA_AQUI'
    
    MES_ATUAL = 'JANEIRO'
    ABA_HISTORICO = 'Histórico'
    
    # Mapeamento das secoes na Planilha (Coordenadas)
    ENTRADAS_INICIO_LINHA = 10
    ENTRADAS_FIM_LINHA = 19
    ENTRADAS_COL_DESCRICAO = 'B'
    ENTRADAS_COL_VALOR = 'C'
    ENTRADAS_COL_DATA = 'D'
    ENTRADAS_COL_CHECKBOX = 'E'
    
    VARIAVEIS_INICIO_LINHA = 25
    VARIAVEIS_FIM_LINHA = 51
    VARIAVEIS_COL_DESCRICAO = 'B'
    VARIAVEIS_COL_VALOR = 'C'
    VARIAVEIS_COL_DATA = 'D'
    VARIAVEIS_COL_CATEGORIA = 'E'
    VARIAVEIS_COL_FORMA = 'F'
    
    FIXOS_INICIO_LINHA = 17
    FIXOS_FIM_LINHA = 26
    FIXOS_COL_DESCRICAO = 'H'
    FIXOS_COL_VALOR = 'I'
    FIXOS_COL_DATA = 'J'
    FIXOS_COL_CATEGORIA = 'K'
    FIXOS_COL_CHECKBOX = 'L'
    
    PASTA_EXTRATOS = 'extratos'
    PASTA_PROCESSADOS = 'extratos/processados'

# ==============================================================================
# ENGINE DE CATEGORIZACAO
# ==============================================================================
class CategorizadorIA:
    
    MAPEAMENTO = {
        'Transporte': ['uber', '99', 'taxi', 'gasolina', 'posto', 'ipva', 'estacionamento', 'onibus', 'metro'],
        'Delivery': ['ifood', 'rappi', 'uber eats', 'delivery'],
        'Lazer': ['cinema', 'netflix', 'spotify', 'prime', 'disney', 'restaurante', 'bar', 'show'],
        'Saude': ['medico', 'hospital', 'laboratorio', 'consulta', 'exame', 'clinica'],
        'Farmacia': ['farmacia', 'droga', 'drogaria', 'remedio'],
        'Casa': ['aluguel', 'condominio', 'luz', 'agua', 'internet', 'gas', 'energia'],
        'Supermercado': ['supermercado', 'mercado', 'atacadao', 'pao de acucar', 'assai', 'padaria'],
        'Roupa': ['roupa', 'sapato', 'loja', 'zara', 'renner', 'nike', 'adidas'],
        'Faculdade': ['faculdade', 'universidade', 'curso', 'mensalidade', 'escola'],
        'Beleza': ['salao', 'cabelo', 'manicure', 'barbeiro', 'estetica'],
        'Assinaturas': ['assinatura', 'recorrente', 'tim', 'vivo', 'claro', 'oi'],
        'Presentes': ['presente', 'gift'],
    }
    
    GASTOS_FIXOS_KEYWORDS = [
        'aluguel', 'condominio', 'luz', 'agua', 'internet', 'gas', 'energia',
        'tim', 'vivo', 'claro', 'oi', 'netflix', 'spotify', 'prime', 'disney',
        'faculdade', 'universidade', 'mensalidade', 'plano', 'assinatura', 'academia'
    ]
    
    @classmethod
    def categorizar(cls, descricao, valor):
        desc = descricao.lower()
        logger.debug(f"Categorizando: '{descricao[:50]}...' | Valor: R$ {valor}")
        
        if valor > 0 or 'recebida' in desc or 'salario' in desc:
            return 'Entrada', 'Receita', False
        
        desc_limpo = desc.replace(' ', '').replace('.', '').replace('-', '')
        eh_fixo = False
        for palavra in cls.GASTOS_FIXOS_KEYWORDS:
            palavra_limpa = palavra.replace(' ', '').replace('.', '').replace('-', '')
            if palavra_limpa in desc_limpo:
                eh_fixo = True
                break
        
        for categoria, palavras in cls.MAPEAMENTO.items():
            if any(palavra in desc for palavra in palavras):
                return categoria, 'Despesa', eh_fixo
        
        return 'Necessidade', 'Despesa', eh_fixo
    
    @classmethod
    def identificar_forma_pagamento(cls, descricao):
        desc = descricao.lower()
        if 'pix' in desc: return 'Pix'
        elif 'cartao' in desc or 'credito' in desc: return 'Cartao'
        else: return 'Pix'

# ==============================================================================
# LEITOR DE EXTRATOS
# ==============================================================================
class LeitorExtratos:
    @staticmethod
    def ler_csv_nubank_brasil(caminho):
        logger.info(f"Lendo CSV: {caminho}")
        try:
            df = pd.read_csv(caminho, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(caminho, encoding='latin1')
        
        colunas_requeridas = ['Data', 'Valor']
        # Logica para encontrar a coluna de descricao independente do nome exato
        colunas_desc = [col for col in df.columns if 'descri' in col.lower()]
        
        if not colunas_desc:
            raise ValueError("CSV invalido: falta coluna de descricao")
        
        df = df.rename(columns={colunas_desc[0]: 'Descricao'})
        df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
        df = df.dropna(subset=['Valor'])
        df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce').dt.strftime('%d/%m/%Y')
        df = df.dropna(subset=['Data'])
        
        return df[['Data', 'Descricao', 'Valor']].copy()
    
    @staticmethod
    def detectar_e_ler(caminho):
        if Path(caminho).suffix.lower() == '.csv':
            return LeitorExtratos.ler_csv_nubank_brasil(caminho)
        raise ValueError("Formato nao suportado")

# ==============================================================================
# INTEGRADOR GOOGLE SHEETS
# ==============================================================================
class IntegradorSheets:
    def __init__(self):
        logger.info("Inicializando conexao com Google Sheets...")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(Config.CREDENCIAIS_JSON, scope)
            self.client = gspread.authorize(creds)
            self.planilha = self.client.open_by_key(Config.PLANILHA_ID)
            self.aba_mes = self.planilha.worksheet(Config.MES_ATUAL)
        except Exception as e:
            logger.error(f"Erro de conexao. Verifique Credenciais e ID da Planilha. Detalhes: {e}")
            raise

    def _gerar_hash_transacao(self, row):
        texto = f"{row['Data']}|{row['Descricao']}|{row['Valor']}"
        return hashlib.md5(texto.encode()).hexdigest()
    
    def _get_transacoes_existentes(self):
        try:
            aba = self.planilha.worksheet(Config.ABA_HISTORICO)
            df = get_as_dataframe(aba, evaluate_formulas=True)
            if 'Hash' not in df.columns: return set()
            return set(df['Hash'].dropna().tolist())
        except gspread.exceptions.WorksheetNotFound:
            self._criar_aba_historico()
            return set()

    def _criar_aba_historico(self):
        aba = self.planilha.add_worksheet(Config.ABA_HISTORICO, 1000, 10)
        aba.update([['Hash', 'Data', 'Descricao', 'Valor', 'Data_Importacao']], 'A1:E1')

    def _encontrar_proxima_linha_vazia(self, coluna, inicio, fim):
        range_notation = f'{coluna}{inicio}:{coluna}{fim}'
        valores = self.aba_mes.get(range_notation, value_render_option='UNFORMATTED_VALUE')
        
        if not valores: return inicio
        
        linha_atual = inicio
        for linha_valores in valores:
            if not linha_valores or linha_valores[0] in [None, '']:
                return linha_atual
            linha_atual += 1
            
        return None # Secao cheia

    def importar_transacoes(self, df):
        logger.info("Iniciando importacao...")
        df['Hash'] = df.apply(self._gerar_hash_transacao, axis=1)
        
        hashes_existentes = self._get_transacoes_existentes()
        df_novas = df[~df['Hash'].isin(hashes_existentes)]
        
        if df_novas.empty:
            logger.info("Nenhuma transacao nova.")
            return

        # Categorizacao e processamento omitidos para brevidade do exemplo publico
        # (O codigo real contem logica de insercao linha a linha nas secoes corretas)
        # ... Logica de insercao mantida do original ...
        
        # Para versao publica simplificada, mantemos a estrutura logica
        # O usuario deve garantir que as funcoes _inserir_* estao implementadas
        # conforme a versao completa local.
        
        # Simulando chamada das funcoes de insercao (que estao no seu codigo original)
        self._processar_insercoes(df_novas)
        self._atualizar_historico(df_novas)

    def _processar_insercoes(self, df):
        # Wrapper para organizar a chamada das insercoes
        resultado = df.apply(lambda row: CategorizadorIA.categorizar(row['Descricao'], row['Valor']), axis=1)
        df['Categoria'] = resultado.apply(lambda x: x[0])
        df['Tipo'] = resultado.apply(lambda x: x[1])
        df['EhFixo'] = resultado.apply(lambda x: x[2])
        df['Forma'] = df['Descricao'].apply(CategorizadorIA.identificar_forma_pagamento)
        
        self._inserir_entradas(df[df['Tipo'] == 'Receita'])
        self._inserir_gastos_fixos(df[(df['Tipo'] == 'Despesa') & (df['EhFixo'] == True)])
        self._inserir_gastos_variaveis(df[(df['Tipo'] == 'Despesa') & (df['EhFixo'] == False)])

    # --- Metodos auxiliares de insercao (simplificados para visualizacao) ---
    def _inserir_entradas(self, df): self._inserir_generico(df, Config.ENTRADAS_COL_DESCRICAO, Config.ENTRADAS_INICIO_LINHA, Config.ENTRADAS_FIM_LINHA)
    def _inserir_gastos_fixos(self, df): self._inserir_generico(df, Config.FIXOS_COL_DESCRICAO, Config.FIXOS_INICIO_LINHA, Config.FIXOS_FIM_LINHA)
    def _inserir_gastos_variaveis(self, df): self._inserir_generico(df, Config.VARIAVEIS_COL_DESCRICAO, Config.VARIAVEIS_INICIO_LINHA, Config.VARIAVEIS_FIM_LINHA)
    
    def _inserir_generico(self, df, col_desc, inicio, fim):
        # Logica de insercao segura com verificacao de espaco
        linha = self._encontrar_proxima_linha_vazia(col_desc, inicio, fim)
        if linha and linha <= fim:
            for _, row in df.iterrows():
                if linha > fim: break
                # Atualiza celulas (Resumido)
                self.aba_mes.update([[str(row['Descricao'])[:50]]], f'{col_desc}{linha}')
                # ... outros campos ...
                linha += 1

    def _atualizar_historico(self, df):
        try:
            aba = self.planilha.worksheet(Config.ABA_HISTORICO)
            valores = aba.get_all_values()
            prox_linha = len(valores) + 1
            df['Data_Importacao'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            dados = df[['Hash', 'Data', 'Descricao', 'Valor', 'Data_Importacao']].values.tolist()
            aba.update(dados, f'A{prox_linha}')
        except Exception as e:
            logger.error(f"Erro ao salvar historico: {e}")

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    logger.info("INICIANDO FINANCAS BOB - AUTOMACAO")
    
    # Verifica se credenciais existem antes de rodar
    if not os.path.exists(Config.CREDENCIAIS_JSON):
        logger.critical(f"Arquivo '{Config.CREDENCIAIS_JSON}' nao encontrado!")
        logger.info("Por favor, adicione suas credenciais do Google Cloud neste local.")
        return

    arquivos = list(Path(Config.PASTA_EXTRATOS).glob('*.csv'))
    if not arquivos:
        logger.warning("Nenhum CSV encontrado.")
        return
        
    df_consolidado = pd.DataFrame()
    for arq in arquivos:
        try:
            df_consolidado = pd.concat([df_consolidado, LeitorExtratos.detectar_e_ler(arq)])
        except: continue
            
    if not df_consolidado.empty:
        IntegradorSheets().importar_transacoes(df_consolidado)
        logger.info("Sucesso! Verifique a planilha.")

if __name__ == "__main__":
    main()