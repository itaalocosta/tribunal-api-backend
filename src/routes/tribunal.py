from flask import Blueprint, jsonify, request
import requests
import re
from datetime import datetime
import logging

tribunal_bp = Blueprint('tribunal', __name__)

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mapeamento de tribunais para a API Datajud
TRIBUNAIS_DATAJUD = {
    # Tribunais Superiores
    'tst': 'Tribunal Superior do Trabalho',
    'stj': 'Superior Tribunal de Justiça', 
    'stf': 'Supremo Tribunal Federal',
    'tse': 'Tribunal Superior Eleitoral',
    'stm': 'Superior Tribunal Militar',
    
    # Justiça Federal
    'trf1': 'Tribunal Regional Federal da 1ª Região',
    'trf2': 'Tribunal Regional Federal da 2ª Região',
    'trf3': 'Tribunal Regional Federal da 3ª Região',
    'trf4': 'Tribunal Regional Federal da 4ª Região',
    'trf5': 'Tribunal Regional Federal da 5ª Região',
    'trf6': 'Tribunal Regional Federal da 6ª Região',
    
    # Justiça Estadual (principais)
    'tjsp': 'Tribunal de Justiça de São Paulo',
    'tjrj': 'Tribunal de Justiça do Rio de Janeiro',
    'tjmg': 'Tribunal de Justiça de Minas Gerais',
    'tjrs': 'Tribunal de Justiça do Rio Grande do Sul',
    'tjpr': 'Tribunal de Justiça do Paraná',
    'tjsc': 'Tribunal de Justiça de Santa Catarina',
    'tjba': 'Tribunal de Justiça da Bahia',
    'tjgo': 'Tribunal de Justiça de Goiás',
    'tjpe': 'Tribunal de Justiça de Pernambuco',
    'tjce': 'Tribunal de Justiça do Ceará',
    'tjdft': 'Tribunal de Justiça do Distrito Federal e dos Territórios',
    
    # Justiça do Trabalho (principais)
    'trt1': 'Tribunal Regional do Trabalho da 1ª Região',
    'trt2': 'Tribunal Regional do Trabalho da 2ª Região',
    'trt3': 'Tribunal Regional do Trabalho da 3ª Região',
    'trt4': 'Tribunal Regional do Trabalho da 4ª Região',
    'trt5': 'Tribunal Regional do Trabalho da 5ª Região',
    'trt15': 'Tribunal Regional do Trabalho da 15ª Região'
}

def validar_numero_processo(numero):
    """Valida e formata número de processo judicial brasileiro"""
    # Remove caracteres não numéricos
    numero_limpo = re.sub(r'[^0-9]', '', numero)
    
    # Verifica se tem 20 dígitos
    if len(numero_limpo) != 20:
        return None
    
    # Formata no padrão NNNNNNN-DD.AAAA.J.TR.OOOO
    return f"{numero_limpo[:7]}-{numero_limpo[7:9]}.{numero_limpo[9:13]}.{numero_limpo[13]}.{numero_limpo[14:16]}.{numero_limpo[16:]}"

def consultar_datajud(tribunal_codigo, numero_processo):
    """Consulta processo na API Pública do Datajud"""
    try:
        url = f"https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal_codigo}/"
        
        # Parâmetros da consulta
        params = {
            'numeroProcesso': numero_processo
        }
        
        headers = {
            'User-Agent': 'TribunalAPI/1.0',
            'Accept': 'application/json'
        }
        
        logger.info(f"Consultando Datajud: {url} - Processo: {numero_processo}")
        
        response = requests.get(url, params=params, headers=headers, timeout=30)
        
        if response.status_code == 200:
            return {
                'sucesso': True,
                'dados': response.json(),
                'fonte': 'Datajud',
                'tribunal': TRIBUNAIS_DATAJUD.get(tribunal_codigo, tribunal_codigo.upper())
            }
        elif response.status_code == 404:
            return {
                'sucesso': False,
                'erro': 'Processo não encontrado',
                'codigo': 404
            }
        else:
            return {
                'sucesso': False,
                'erro': f'Erro na API: {response.status_code}',
                'codigo': response.status_code
            }
            
    except requests.exceptions.Timeout:
        return {
            'sucesso': False,
            'erro': 'Timeout na consulta',
            'codigo': 408
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro na consulta Datajud: {str(e)}")
        return {
            'sucesso': False,
            'erro': f'Erro de conexão: {str(e)}',
            'codigo': 500
        }

def identificar_tribunal_por_numero(numero_processo):
    """Identifica o tribunal baseado no número do processo"""
    numero_limpo = re.sub(r'[^0-9]', '', numero_processo)
    
    if len(numero_limpo) != 20:
        return None
    
    # Extrai o código do tribunal (posições 13-16)
    codigo_tribunal = numero_limpo[13:16]
    
    # Mapeamento básico de códigos de tribunal
    mapeamento_tribunais = {
        '1': 'stf',    # STF
        '2': 'stj',    # STJ
        '3': 'trf1',   # TRF1
        '4': 'trf2',   # TRF2
        '5': 'trf3',   # TRF3
        '6': 'trf4',   # TRF4
        '7': 'trf5',   # TRF5
        '8': 'tjsp',   # TJSP (exemplo)
        '9': 'tjrj',   # TJRJ (exemplo)
    }
    
    # Retorna o código do tribunal ou tenta inferir
    return mapeamento_tribunais.get(codigo_tribunal[0], 'tjsp')  # Default para TJSP

@tribunal_bp.route('/tribunais', methods=['GET'])
def listar_tribunais():
    """Lista todos os tribunais disponíveis"""
    tribunais = []
    for codigo, nome in TRIBUNAIS_DATAJUD.items():
        tribunais.append({
            'codigo': codigo,
            'nome': nome,
            'disponivel': True
        })
    
    return jsonify({
        'sucesso': True,
        'tribunais': tribunais,
        'total': len(tribunais)
    })

@tribunal_bp.route('/processo/<numero>', methods=['GET'])
def consultar_processo(numero):
    """Consulta processo por número (detecta tribunal automaticamente)"""
    # Valida número do processo
    numero_formatado = validar_numero_processo(numero)
    if not numero_formatado:
        return jsonify({
            'sucesso': False,
            'erro': 'Número de processo inválido. Deve conter 20 dígitos.'
        }), 400
    
    # Identifica tribunal
    tribunal_codigo = identificar_tribunal_por_numero(numero)
    if not tribunal_codigo:
        return jsonify({
            'sucesso': False,
            'erro': 'Não foi possível identificar o tribunal'
        }), 400
    
    # Consulta o processo
    resultado = consultar_datajud(tribunal_codigo, numero_formatado)
    
    if resultado['sucesso']:
        return jsonify(resultado)
    else:
        return jsonify(resultado), resultado.get('codigo', 500)

@tribunal_bp.route('/tribunal/<codigo>/processo/<numero>', methods=['GET'])
def consultar_processo_tribunal_especifico(codigo, numero):
    """Consulta processo em tribunal específico"""
    # Valida código do tribunal
    if codigo not in TRIBUNAIS_DATAJUD:
        return jsonify({
            'sucesso': False,
            'erro': f'Tribunal {codigo} não suportado'
        }), 400
    
    # Valida número do processo
    numero_formatado = validar_numero_processo(numero)
    if not numero_formatado:
        return jsonify({
            'sucesso': False,
            'erro': 'Número de processo inválido. Deve conter 20 dígitos.'
        }), 400
    
    # Consulta o processo
    resultado = consultar_datajud(codigo, numero_formatado)
    
    if resultado['sucesso']:
        return jsonify(resultado)
    else:
        return jsonify(resultado), resultado.get('codigo', 500)

@tribunal_bp.route('/consulta/multipla', methods=['POST'])
def consulta_multipla():
    """Consulta processo em múltiplos tribunais simultaneamente"""
    data = request.get_json()
    
    if not data or 'numero_processo' not in data:
        return jsonify({
            'sucesso': False,
            'erro': 'Número do processo é obrigatório'
        }), 400
    
    numero = data['numero_processo']
    tribunais = data.get('tribunais', list(TRIBUNAIS_DATAJUD.keys())[:5])  # Limita a 5 por padrão
    
    # Valida número do processo
    numero_formatado = validar_numero_processo(numero)
    if not numero_formatado:
        return jsonify({
            'sucesso': False,
            'erro': 'Número de processo inválido. Deve conter 20 dígitos.'
        }), 400
    
    resultados = []
    
    for tribunal_codigo in tribunais:
        if tribunal_codigo in TRIBUNAIS_DATAJUD:
            resultado = consultar_datajud(tribunal_codigo, numero_formatado)
            resultado['tribunal_codigo'] = tribunal_codigo
            resultados.append(resultado)
    
    # Conta sucessos
    sucessos = sum(1 for r in resultados if r['sucesso'])
    
    return jsonify({
        'sucesso': True,
        'numero_processo': numero_formatado,
        'tribunais_consultados': len(resultados),
        'encontrados': sucessos,
        'resultados': resultados
    })

@tribunal_bp.route('/status', methods=['GET'])
def status_api():
    """Retorna status da API e conectividade com tribunais"""
    status_tribunais = []
    
    # Testa conectividade com alguns tribunais principais
    tribunais_teste = ['tjsp', 'stj', 'trf1']
    
    for tribunal in tribunais_teste:
        try:
            url = f"https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/"
            response = requests.get(url, timeout=5)
            status_tribunais.append({
                'tribunal': tribunal,
                'nome': TRIBUNAIS_DATAJUD[tribunal],
                'status': 'online' if response.status_code in [200, 400] else 'offline',
                'codigo_resposta': response.status_code
            })
        except:
            status_tribunais.append({
                'tribunal': tribunal,
                'nome': TRIBUNAIS_DATAJUD[tribunal],
                'status': 'offline',
                'codigo_resposta': None
            })
    
    return jsonify({
        'api_status': 'online',
        'timestamp': datetime.now().isoformat(),
        'tribunais_testados': status_tribunais,
        'total_tribunais_disponiveis': len(TRIBUNAIS_DATAJUD)
    })

@tribunal_bp.route('/validar/<numero>', methods=['GET'])
def validar_processo(numero):
    """Valida formato do número de processo"""
    numero_formatado = validar_numero_processo(numero)
    
    if numero_formatado:
        tribunal_codigo = identificar_tribunal_por_numero(numero)
        return jsonify({
            'valido': True,
            'numero_formatado': numero_formatado,
            'tribunal_identificado': tribunal_codigo,
            'tribunal_nome': TRIBUNAIS_DATAJUD.get(tribunal_codigo, 'Desconhecido')
        })
    else:
        return jsonify({
            'valido': False,
            'erro': 'Número de processo deve conter exatamente 20 dígitos'
        }), 400

