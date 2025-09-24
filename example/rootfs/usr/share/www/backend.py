#!/usr/bin/env python3
# backend.py - Flask backend for Add-on (with switch + number control)
from flask import Flask, request, jsonify, send_from_directory
import os, requests, logging, time

app = Flask(__name__, static_folder='.', static_url_path='')

HA_PROXY = os.environ.get('HA_PROXY', 'http://supervisor/core/api')
SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN')

if not SUPERVISOR_TOKEN:
    app.logger.warning("SUPERVISOR_TOKEN not found in environment; HA calls may fail.")

def ha_headers():
    return {
        'Authorization': f'Bearer {SUPERVISOR_TOKEN}',
        'Content-Type': 'application/json'
    }

def ha_get(path):
    url = f"{HA_PROXY}{path}"
    r = requests.get(url, headers=ha_headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def ha_post(path, payload):
    url = f"{HA_PROXY}{path}"
    r = requests.post(url, headers=ha_headers(), json=payload, timeout=10)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        return {'status_code': r.status_code}

# caching for /states
_STATES_CACHE = {'ts': 0, 'data': None}
_STATES_TTL = 3.0

def get_states_cached():
    now = time.time()
    if _STATES_CACHE['data'] is None or (now - _STATES_CACHE['ts']) > _STATES_TTL:
        _STATES_CACHE['data'] = ha_get('/states')
        _STATES_CACHE['ts'] = now
    return _STATES_CACHE['data']

@app.before_request
def log_req():
    try:
        app.logger.info("REQ %s %s from %s", request.method, request.path, request.remote_addr)
    except Exception:
        pass

def build_node_map(domain_whitelist=('switch','sensor','number','light','binary_sensor')):
    try:
        states = get_states_cached()
    except Exception as e:
        app.logger.exception("Failed to fetch states: %s", e)
        return {}

    node_map = {}
    for s in states:
        eid = s.get('entity_id','')
        if '.' not in eid:
            continue
        domain, rest = eid.split('.',1)
        if domain not in domain_whitelist:
            continue
        token = rest.split('_')[0] if '_' in rest else rest.split('.')[0]
        if not token:
            continue
        entry = node_map.setdefault(token, {'node': token, 'entities': {}, 'repr': {}})
        entry['entities'].setdefault(domain, []).append(eid)

    def pick_representative(eids, node):
        if not eids:
            return None
        for e in eids:
            part = e.split('.',1)[1]
            if part.startswith(node + '_'):
                return e
        for e in eids:
            if f".{node}." in e:
                return e
        for e in eids:
            if e.split('.',1)[1].startswith(node):
                return e
        for e in eids:
            if node in e:
                return e
        return eids[0]

    for node, info in node_map.items():
        for domain, eids in info['entities'].items():
            info['repr'][domain] = pick_representative(eids, node)

    return node_map

@app.route('/api/nodes', methods=['GET'])
def api_nodes():
    try:
        nm = build_node_map()
    except Exception as e:
        return jsonify({'error':'discover_failed','message': str(e)}), 500

    out = []
    for node, info in nm.items():
        reprs = info.get('repr', {})
        item = {
            'node': node,
            'switch': reprs.get('switch'),
            'sensor': reprs.get('sensor'),
            'number': reprs.get('number'),
            'light': reprs.get('light'),
            # placeholders
            'switch_name': None,
            'switch_state': None,
            'number_name': None,
            'number_state': None,
            'number_attrs': None,
            'sensor_name': None,
            'sensor_state': None
        }
        # fetch state + friendly_name + attributes for useful domains
        for domain in ('switch','number','sensor'):
            eid = reprs.get(domain)
            if not eid:
                continue
            try:
                st = ha_get(f"/states/{eid}")
                name = st.get('attributes', {}).get('friendly_name') or eid
                if domain == 'switch':
                    item['switch_name'] = name
                    item['switch_state'] = st.get('state')
                elif domain == 'number':
                    item['number_name'] = name
                    item['number_state'] = st.get('state')
                    item['number_attrs'] = st.get('attributes', {})
                elif domain == 'sensor':
                    item['sensor_name'] = name
                    item['sensor_state'] = st.get('state')
            except Exception:
                app.logger.exception("Failed to fetch state for %s", eid)
        out.append(item)
    out.sort(key=lambda x: x['node'])
    return jsonify(out)

@app.route('/api/action', methods=['POST'])
def api_action():
    """
    POST { "node": "<node>", "action": "on"/"off"/"toggle" }
    Controls representative switch.
    """
    data = request.get_json(silent=True) or {}
    node = data.get('node')
    action = (data.get('action') or 'toggle').lower()
    if not node:
        return jsonify({'error':'no_node'}), 400
    if action not in ('on','off','toggle'):
        return jsonify({'error':'invalid_action'}), 400

    nm = build_node_map()
    info = nm.get(node)
    if not info:
        return jsonify({'error':'node_not_found'}), 404

    switch_eid = info.get('repr', {}).get('switch')
    if not switch_eid:
        return jsonify({'error':'no_switch_for_node'}), 400

    domain = switch_eid.split('.',1)[0]
    service_name = {'on':'turn_on','off':'turn_off','toggle':'toggle'}[action]

    try:
        result = ha_post(f"/services/{domain}/{service_name}", {'entity_id': switch_eid})
    except requests.HTTPError as e:
        app.logger.exception("Service call failed")
        return jsonify({'error':'service_failed','message': str(e)}), 500

    return jsonify({'status':'ok','entity': switch_eid, 'action': action, 'result': result})

@app.route('/api/set_number', methods=['POST'])
def api_set_number():
    """
    POST { "node": "<node>", "value": <number> }
    Calls number.set_value on representative number entity.
    """
    data = request.get_json(silent=True) or {}
    node = data.get('node')
    value = data.get('value')
    if not node:
        return jsonify({'error':'no_node'}), 400
    try:
        val = float(value)
    except Exception:
        return jsonify({'error':'invalid_value'}), 400

    nm = build_node_map()
    info = nm.get(node)
    if not info:
        return jsonify({'error':'node_not_found'}), 404

    number_eid = info.get('repr', {}).get('number')
    if not number_eid:
        return jsonify({'error':'no_number_for_node'}), 400

    try:
        result = ha_post("/services/number/set_value", {'entity_id': number_eid, 'value': val})
    except requests.HTTPError as e:
        app.logger.exception("Number service call failed")
        return jsonify({'error':'service_failed','message': str(e)}), 500

    return jsonify({'status':'ok','entity': number_eid, 'value': val, 'result': result})

# static routes
@app.route('/', methods=['GET'])
def index():
    return send_from_directory('.', 'index.html')

@app.route('/index.html', methods=['GET'])
def index_html():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>', methods=['GET'])
def static_file(filename):
    return send_from_directory('.', filename)

@app.route('/api/state/<path:entity_id>', methods=['GET'])
def api_state(entity_id):
    try:
        st = ha_get(f"/states/{entity_id}")
        return jsonify(st)
    except Exception as e:
        return jsonify({'error':'failed','message': str(e)}), 500

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get('PORT', 8199))
    app.run(host='0.0.0.0', port=port)
