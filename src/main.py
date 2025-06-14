import os
import sys
import uuid
import hashlib
import json
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, List, Optional

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
from src.models.user import db
from src.routes.user import user_bp
from src.routes.tribunal import tribunal_bp

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'

# Habilitar CORS para todas as rotas
CORS(app)

# Sistema de gerenciamento de chaves de API
API_KEYS_FILE = os.path.join(os.path.dirname(__file__), 'database', 'api_keys.json')
USAGE_STATS_FILE = os.path.join(os.path.dirname(__file__), 'database', 'usage_stats.json')

def ensure_database_dir():
    """Garante que o diretório database existe"""
    db_dir = os.path.join(os.path.dirname(__file__), 'database')
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)

def load_api_keys():
    """Carrega chaves de API do arquivo"""
    try:
        with open(API_KEYS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_api_keys(keys_data):
    """Salva chaves de API no arquivo"""
    ensure_database_dir()
    with open(API_KEYS_FILE, 'w') as f:
        json.dump(keys_data, f, indent=2)

def load_usage_stats():
    """Carrega estatísticas de uso do arquivo"""
    try:
        with open(USAGE_STATS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_usage_stats(stats_data):
    """Salva estatísticas de uso no arquivo"""
    ensure_database_dir()
    with open(USAGE_STATS_FILE, 'w') as f:
        json.dump(stats_data, f, indent=2)

def generate_api_key():
    """Gera uma nova chave de API única"""
    return f"tk_{uuid.uuid4().hex[:24]}"

def hash_api_key(api_key):
    """Cria hash da chave de API para armazenamento seguro"""
    return hashlib.sha256(api_key.encode()).hexdigest()

def validate_api_key(f):
    """Decorator para validar chave de API"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({
                'error': 'API key required',
                'message': 'Forneça uma chave de API válida no header X-API-Key ou parâmetro api_key'
            }), 401
        
        keys_data = load_api_keys()
        key_hash = hash_api_key(api_key)
        
        if key_hash not in keys_data:
            return jsonify({
                'error': 'Invalid API key',
                'message': 'Chave de API inválida ou revogada'
            }), 401
        
        key_info = keys_data[key_hash]
        
        # Verificar se a chave está ativa
        if not key_info.get('active', True):
            return jsonify({
                'error': 'API key disabled',
                'message': 'Chave de API desativada'
            }), 401
        
        # Verificar expiração
        if key_info.get('expires_at'):
            expires_at = datetime.fromisoformat(key_info['expires_at'])
            if datetime.now() > expires_at:
                return jsonify({
                    'error': 'API key expired',
                    'message': 'Chave de API expirada'
                }), 401
        
        # Verificar limites de uso
        if not check_usage_limits(api_key, key_info):
            return jsonify({
                'error': 'Usage limit exceeded',
                'message': 'Limite de uso excedido para esta chave de API'
            }), 429
        
        # Registrar uso
        record_api_usage(api_key, request.endpoint)
        
        # Adicionar informações da chave ao request
        request.api_key_info = key_info
        
        return f(*args, **kwargs)
    
    return decorated_function

def check_usage_limits(api_key, key_info):
    """Verifica se a chave ainda está dentro dos limites de uso"""
    limits = key_info.get('limits', {})
    if limits.get('daily', -1) == -1 and limits.get('monthly', -1) == -1:
        return True  # Ilimitado
    
    stats = load_usage_stats()
    key_hash = hash_api_key(api_key)
    
    if key_hash not in stats:
        return True  # Primeira vez usando
    
    today = datetime.now().strftime('%Y-%m-%d')
    month = datetime.now().strftime('%Y-%m')
    
    # Verificar limite diário
    daily_limit = limits.get('daily', -1)
    if daily_limit > 0:
        today_usage = stats[key_hash].get(today, {}).get('total', 0)
        if today_usage >= daily_limit:
            return False
    
    # Verificar limite mensal
    monthly_limit = limits.get('monthly', -1)
    if monthly_limit > 0:
        monthly_usage = 0
        for date, usage in stats[key_hash].items():
            if date.startswith(month):
                monthly_usage += usage.get('total', 0)
        if monthly_usage >= monthly_limit:
            return False
    
    return True

def record_api_usage(api_key, endpoint):
    """Registra uso da API para estatísticas"""
    stats = load_usage_stats()
    key_hash = hash_api_key(api_key)
    today = datetime.now().strftime('%Y-%m-%d')
    
    if key_hash not in stats:
        stats[key_hash] = {}
    
    if today not in stats[key_hash]:
        stats[key_hash][today] = {'total': 0, 'endpoints': {}}
    
    stats[key_hash][today]['total'] += 1
    
    if endpoint not in stats[key_hash][today]['endpoints']:
        stats[key_hash][today]['endpoints'][endpoint] = 0
    
    stats[key_hash][today]['endpoints'][endpoint] += 1
    
    save_usage_stats(stats)

# Endpoints de gerenciamento de API Keys
@app.route('/admin/api-keys', methods=['POST'])
def create_api_key():
    """Cria uma nova chave de API"""
    data = request.get_json() or {}
    
    # Gerar nova chave
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    
    # Configurações da chave
    key_info = {
        'name': data.get('name', 'Unnamed Key'),
        'email': data.get('email', ''),
        'plan': data.get('plan', 'free'),  # free, basic, professional, enterprise
        'created_at': datetime.now().isoformat(),
        'active': True,
        'limits': {
            'free': {'daily': 10, 'monthly': 30},
            'basic': {'daily': 50, 'monthly': 1000},
            'professional': {'daily': 200, 'monthly': 5000},
            'enterprise': {'daily': -1, 'monthly': -1}  # -1 = ilimitado
        }.get(data.get('plan', 'free'), {'daily': 10, 'monthly': 30})
    }
    
    # Definir expiração se especificada
    if data.get('expires_in_days'):
        expires_at = datetime.now() + timedelta(days=data['expires_in_days'])
        key_info['expires_at'] = expires_at.isoformat()
    
    # Salvar chave
    keys_data = load_api_keys()
    keys_data[key_hash] = key_info
    save_api_keys(keys_data)
    
    return jsonify({
        'api_key': api_key,
        'info': key_info,
        'message': 'Chave de API criada com sucesso'
    })

@app.route('/admin/api-keys', methods=['GET'])
def list_api_keys():
    """Lista todas as chaves de API (sem mostrar as chaves reais)"""
    keys_data = load_api_keys()
    
    keys_list = []
    for key_hash, info in keys_data.items():
        keys_list.append({
            'id': key_hash[:8] + '...',  # Mostrar apenas parte do hash
            'name': info.get('name'),
            'email': info.get('email'),
            'plan': info.get('plan'),
            'created_at': info.get('created_at'),
            'active': info.get('active'),
            'expires_at': info.get('expires_at')
        })
    
    return jsonify({
        'keys': keys_list,
        'total': len(keys_list)
    })

@app.route('/admin/api-keys/<key_id>', methods=['DELETE'])
def revoke_api_key(key_id):
    """Revoga uma chave de API"""
    keys_data = load_api_keys()
    
    # Encontrar chave pelo ID parcial
    target_key = None
    for key_hash in keys_data:
        if key_hash.startswith(key_id.replace('...', '')):
            target_key = key_hash
            break
    
    if not target_key:
        return jsonify({
            'error': 'Key not found',
            'message': 'Chave de API não encontrada'
        }), 404
    
    # Desativar chave
    keys_data[target_key]['active'] = False
    keys_data[target_key]['revoked_at'] = datetime.now().isoformat()
    save_api_keys(keys_data)
    
    return jsonify({
        'message': 'Chave de API revogada com sucesso'
    })

@app.route('/admin/usage/<key_id>', methods=['GET'])
def get_usage_stats_endpoint(key_id):
    """Obtém estatísticas de uso de uma chave"""
    stats = load_usage_stats()
    
    # Encontrar estatísticas pelo ID parcial
    target_stats = None
    for key_hash in stats:
        if key_hash.startswith(key_id.replace('...', '')):
            target_stats = stats[key_hash]
            break
    
    if not target_stats:
        return jsonify({
            'usage': {},
            'total_requests': 0
        })
    
    # Calcular totais
    total_requests = 0
    for date_stats in target_stats.values():
        total_requests += date_stats.get('total', 0)
    
    return jsonify({
        'usage': target_stats,
        'total_requests': total_requests
    })

@app.route('/admin/dashboard', methods=['GET'])
def admin_dashboard():
    """Dashboard administrativo com estatísticas gerais"""
    keys_data = load_api_keys()
    stats = load_usage_stats()
    
    # Estatísticas gerais
    total_keys = len(keys_data)
    active_keys = sum(1 for info in keys_data.values() if info.get('active', True))
    
    # Uso por plano
    plans_usage = {}
    for info in keys_data.values():
        plan = info.get('plan', 'free')
        if plan not in plans_usage:
            plans_usage[plan] = 0
        plans_usage[plan] += 1
    
    # Uso total hoje
    today = datetime.now().strftime('%Y-%m-%d')
    today_requests = 0
    for key_stats in stats.values():
        if today in key_stats:
            today_requests += key_stats[today].get('total', 0)
    
    return jsonify({
        'total_keys': total_keys,
        'active_keys': active_keys,
        'plans_distribution': plans_usage,
        'today_requests': today_requests,
        'revenue_estimate': {
            'basic': plans_usage.get('basic', 0) * 29.90,
            'professional': plans_usage.get('professional', 0) * 99.90,
            'enterprise': plans_usage.get('enterprise', 0) * 299.90
        }
    })

# Registrar blueprints com validação de API key
app.register_blueprint(user_bp, url_prefix='/api')

# Criar blueprint protegido para tribunal
from flask import Blueprint
tribunal_protected_bp = Blueprint('tribunal_protected', __name__)

@tribunal_protected_bp.route('/processo/<numero>', methods=['GET'])
@validate_api_key
def consultar_processo_protegido(numero):
    """Consulta processo com validação de API key"""
    from src.routes.tribunal import consultar_processo
    return consultar_processo(numero)

@tribunal_protected_bp.route('/validar/<numero>', methods=['GET'])
@validate_api_key
def validar_processo_protegido(numero):
    """Valida processo com validação de API key"""
    from src.routes.tribunal import validar_processo
    return validar_processo(numero)

@tribunal_protected_bp.route('/consulta/multipla', methods=['POST'])
@validate_api_key
def consulta_multipla_protegida():
    """Consulta múltipla com validação de API key"""
    from src.routes.tribunal import consulta_multipla
    return consulta_multipla()

app.register_blueprint(tribunal_protected_bp, url_prefix='/api')

# Endpoints públicos (sem autenticação) - registrar o blueprint original também
app.register_blueprint(tribunal_bp, url_prefix='/api/public')

# uncomment if you need to use database
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

if __name__ == '__main__':
    # Inicializar arquivos de dados
    ensure_database_dir()
    if not os.path.exists(API_KEYS_FILE):
        save_api_keys({})
    if not os.path.exists(USAGE_STATS_FILE):
        save_usage_stats({})
    
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)

