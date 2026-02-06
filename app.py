import requests
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import re
import json
import os
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()]
)

BASE_URL_API = os.getenv("BASE_URL_API")
TOKEN_API = os.getenv("API_TOKEN") 

API_AUTH_URL = os.getenv("API_AUTH_URL")
API_USER = os.getenv("API_USER")
API_PASS = os.getenv("API_PASS")

URL_HSM = os.getenv("HSM_URL")
TOKEN_HSM = os.getenv("HSM_TOKEN")
COOKIE_HSM = os.getenv("HSM_COOKIE")

HSM_ID_LOS = 114       
HSM_ID_ENERGIA = 116   

ARQUIVO_STATUS = "status_incidentes.json"
ARQUIVO_LOGS = "historico_logs.json"
ARQUIVO_AGUARDA_24H = "controle_prox_envio.json"

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {TOKEN_API}",
    "Content-Type": "application/json"
})

def renovar_token():
    logging.info("Tentando renovar token da API...")
    
    payload = {
        "username": API_USER,
        "password": API_PASS
    }
    
    try:
        resp = requests.post(API_AUTH_URL, json=payload, timeout=10)
        
        if resp.status_code == 200:
            novo_token = resp.json().get('access')
            
            if novo_token:
                session.headers.update({"Authorization": f"Bearer {novo_token}"})
                logging.info("Token renovado.")
                return True
            else:
                logging.error("Token não encontrado")
        else:
            logging.error(f"Falha no login: {resp.status_code} - {resp.text}")
            
    except Exception as e:
        logging.error(f"Erro ao conectar no endpoint de login: {e}")
        
    return False

def safe_api_get(url, timeout=10):
    try:
        response = session.get(url, timeout=timeout)
        
        if response.status_code == 401:
            logging.warning("Token expirado (401). Iniciando renovação...")
            if renovar_token():
                return session.get(url, timeout=timeout)
            else:
                logging.error("Não foi possível renovar o token.")
                return response
                
        return response
    except Exception as e:
        logging.error(f"Erro na requisição GET: {e}")
        return None

def carregar_json(arquivo):
    if not os.path.exists(arquivo): return {} if arquivo != ARQUIVO_LOGS else []
    try:
        with open(arquivo, 'r') as f: return json.load(f)
    except: return {} if arquivo != ARQUIVO_LOGS else []

def salvar_status_id(id_incidente, status):
    dados = carregar_json(ARQUIVO_STATUS)
    dados[str(id_incidente)] = status
    with open(ARQUIVO_STATUS, 'w') as f: json.dump(dados, f, indent=4)

def salvar_log_completo(snapshot, acao, sucesso=True):
    historico = carregar_json(ARQUIVO_LOGS)
    registro = {
        "id": snapshot.get('id'),
        "data_acao": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "acao": acao,
        "status_envio": "Sucesso" if sucesso else "Falha/Parcial",
        "snapshot": snapshot
    }
    historico.insert(0, registro)
    with open(ARQUIVO_LOGS, 'w') as f: json.dump(historico, f, indent=4)

def verificar_em_cooldown(chave_unica):
    dados = carregar_json(ARQUIVO_AGUARDA_24H)
    ultima_data_str = dados.get(chave_unica)
    if not ultima_data_str: return False
    try:
        ultima_data = datetime.strptime(ultima_data_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - ultima_data < timedelta(hours=24): return True
        return False
    except: return False

def registrar_disparo_cooldown(chave_unica):
    dados = carregar_json(ARQUIVO_AGUARDA_24H)
    dados[chave_unica] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ARQUIVO_AGUARDA_24H, 'w') as f: json.dump(dados, f, indent=4)

def gerar_chave_incidente(item):
    olt = item.get('olt_name', 'UNK')
    slot = item.get('slot_pon', 'UNK')
    tipo = item.get('alert_type', 'UNK')
    return f"{olt}|{slot}|{tipo}"

def formatar_telefone(numero_raw):
    if not numero_raw: return None
    limpo = re.sub(r'\D', '', str(numero_raw))
    if len(limpo) < 10: return None
    if limpo.startswith('55') and len(limpo) >= 12: return limpo
    return f"55{limpo}"

def determinar_causa(tipo_alerta, qtd_afetada):
    if tipo_alerta == "pon_no_power": return "Provável Falha de Energia"
    if tipo_alerta == "pon_loss": return "Provável CTO LOS" if qtd_afetada <= 16 else "Provável Rompimento de Fibra"
    return "Verificar Incidente"

def executar_curl_hsm(telefone_formatado, nome_cliente, tipo_alerta):
    if not telefone_formatado: return False
    
    template_id = HSM_ID_ENERGIA if tipo_alerta == "pon_no_power" else HSM_ID_LOS
    
    logging.info(f"[HSM] Enviando ID {template_id} para {nome_cliente}...")
    
    payload = {
        "cod_conta": 1, "hsm": template_id, "tipo_envio": 2, 
        "contato": { "nome": str(nome_cliente), "telefone": telefone_formatado }
    }
    headers = {
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Authorization': TOKEN_HSM, 'Cookie': COOKIE_HSM       
    }
    try:
        r = requests.post(URL_HSM, json=payload, headers=headers, timeout=15)
        return r.status_code in [200, 201]
    except Exception as e:
        logging.error(f"[HSM] Erro: {e}")
        return False

def get_detalhes_interno(id_incidente):
    try:
        url = f"{BASE_URL_API}/api/v2/ftth/alert/{id_incidente}"
        resp = safe_api_get(url)
        
        if not resp or resp.status_code != 200: return None
        
        alert = resp.json().get('alert', {})
        tipo = alert.get('alert_type')
        slot = alert.get('slot_pon', '-')
        devices = alert.get('affected_devices', [])
        qtd = len(devices)
        
        snapshot = {
            "id": alert.get('id'), "alert_type": tipo,
            "olt_name": alert.get('olt_name', 'OLT'), "slot_pon": slot,
            "total_devices_count": qtd, "initial_date": alert.get('initial_date'),
            "causa_provavel": determinar_causa(tipo, qtd)
        }

        def processar(device):
            onu = device.get('onu_device', {})
            cid = device.get('client_id') or onu.get('client_id')
            obj = {
                "client_id": cid, "sn_onu": onu.get('sn_onu', 'N/A'),
                "client_name": onu.get('client_name', 'Cliente'),
                "status": onu.get('status', 'Offline'), "slot_pon": slot, "contact": None
            }
            if cid:
                try:
                    r = safe_api_get(f"{BASE_URL_API}/api/v2/client/{cid}", timeout=10)
                    if r and r.status_code == 200:
                        clis = r.json().get('clients', [])
                        if clis:
                            raw = clis[0].get('contact') or clis[0].get('phone_number')
                            obj['contact'] = formatar_telefone(raw)
                            if clis[0].get('name'): obj['client_name'] = clis[0].get('name')
                except: pass
            return obj

        clientes = []
        if devices:
            with ThreadPoolExecutor(max_workers=20) as ex:
                clientes = list(ex.map(processar, devices))

        return { "snapshot": snapshot, "clientes": clientes }
    except Exception as e: 
        logging.error(f"Erro detalhes: {e}")
        return None

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/incidentes')
def listar():
    try:
        decisoes = carregar_json(ARQUIVO_STATUS)
        resp = safe_api_get(f"{BASE_URL_API}/api/v2/ftth/alert/list?end_date__isnull=true")
        
        lista = []
        if resp and resp.status_code == 200:
            for item in resp.json().get('results', []):
                if str(item.get('id')) in decisoes: continue
                if item.get('alert_type') not in ['pon_loss', 'pon_no_power']: continue
                if verificar_em_cooldown(gerar_chave_incidente(item)): continue
                lista.append(item)
        return jsonify(lista)
    except Exception as e:
        logging.error(f"Erro listar: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/detalhes/<int:id_inc>')
def detalhes(id_inc):
    d = get_detalhes_interno(id_inc)
    return jsonify({"info": d['snapshot'], "clientes": d['clientes']}) if d else (jsonify({"error": "Erro"}), 500)

@app.route('/api/historico')
def historico():
    logs = carregar_json(ARQUIVO_LOGS)
    
    ativos_keys = set()
    try:
        resp = safe_api_get(f"{BASE_URL_API}/api/v2/ftth/alert/list?end_date__isnull=true", timeout=5)
        if resp and resp.status_code == 200:
            for item in resp.json().get('results', []):
                ativos_keys.add(gerar_chave_incidente(item))
    except: pass

    logs_enrich = []
    agora = datetime.now()

    for log in logs:
        snap = log.get('snapshot', {})
        chave = f"{snap.get('olt_name')}|{snap.get('slot_pon')}|{snap.get('alert_type')}"
        
        log['status_atual'] = "ATIVO" if chave in ativos_keys else "NORMALIZADO"
        
        try:
            dt_acao = datetime.strptime(log['data_acao'], "%d/%m/%Y %H:%M:%S")
            if log['acao'] == 'NEGADO':
                log['liberacao'] = "Imediata"
            else:
                if agora - dt_acao < timedelta(hours=24):
                    libera_em = dt_acao + timedelta(hours=24)
                    log['liberacao'] = libera_em.strftime("%d/%m %H:%M")
                else:
                    log['liberacao'] = "Disponível"
        except:
            log['liberacao'] = "-"
            
        logs_enrich.append(log)

    return jsonify(logs_enrich)

@app.route('/api/acao', methods=['POST'])
def acao():
    d = request.json
    id_inc, acao = d.get('id'), d.get('acao')
    dados = get_detalhes_interno(id_inc)
    if not dados: return jsonify({"success": False, "msg": "Erro dados"}), 500
    
    snap, clis = dados['snapshot'], dados['clientes']
    
    if acao == 'negar':
        salvar_log_completo(snap, 'NEGADO')
        salvar_status_id(id_inc, 'NEGADO')
        return jsonify({"success": True, "msg": "Negado."})

    sucessos = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(executar_curl_hsm, c.get('contact'), c.get('client_name'), snap.get('alert_type')) for c in clis if c.get('contact')]
        for f in futures: 
            if f.result(): sucessos += 1
            
    salvar_log_completo(snap, 'APROVADO', sucesso=(sucessos > 0))
    salvar_status_id(id_inc, 'APROVADO')
    registrar_disparo_cooldown(gerar_chave_incidente(snap))
    
    return jsonify({"success": True, "msg": f"Enviados: {sucessos}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)