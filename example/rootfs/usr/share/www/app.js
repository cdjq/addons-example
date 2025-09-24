// app.js - frontend for ESPHome Node Control with switch + number
const selectEl = document.getElementById('device-select');
const resultEl = document.getElementById('result');
const refreshBtn = document.getElementById('refresh-btn');

let nodesCache = []; // store last nodes list

function apiUrl(path) {
  const href = window.location.href;
  const m = href.match(/(.*\/api\/hassio_ingress\/[^\/]+\/)/);
  if (m) return m[1] + path;
  return path;
}

async function loadNodes() {
  selectEl.innerHTML = '<option>Loading...</option>';
  resultEl.textContent = '';
  try {
    const url = apiUrl('api/nodes');
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('fetch failed: ' + resp.status);
    const nodes = await resp.json();
    nodesCache = nodes;
    selectEl.innerHTML = '';
    if (!Array.isArray(nodes) || nodes.length === 0) {
      selectEl.innerHTML = '<option value="">No nodes found</option>';
      return;
    }
    nodes.forEach(n => {
      const opt = document.createElement('option');
      opt.value = n.node;
      const label = (n.switch_name ? `${n.switch_name}` : n.node) + ` (${n.node})`;
      opt.textContent = label;
      selectEl.appendChild(opt);
    });
    // select first item by default
    if (!selectEl.value) selectEl.selectedIndex = 0;
    renderSelectedNodeDetails();
    selectEl.onchange = () => renderSelectedNodeDetails();
  } catch (err) {
    console.error(err);
    selectEl.innerHTML = '<option value="">Load error</option>';
    resultEl.textContent = 'Error loading nodes: ' + (err.message || err);
  }
}

function renderSelectedNodeDetails() {
  const node = selectEl.value;
  if (!node) {
    resultEl.textContent = 'No node selected';
    return;
  }
  const info = nodesCache.find(n => n.node === node);
  if (!info) {
    resultEl.textContent = 'Selected node not found in cache';
    return;
  }
  // show switch state and number input
  const switchState = info.switch_state;
  const numberState = info.number_state;
  const numberAttrs = info.number_attrs || {};

  // render interactive controls below (reuse the resultEl for status)
  let html = `Node: ${node}\n`;
  if (info.switch) {
    html += `Switch: ${info.switch_name || info.switch} -> ${switchState}\n`;
    html += `[Use buttons below to control switch]\n`;
  } else {
    html += `Switch: (not found)\n`;
  }
  if (info.number) {
    html += `Number: ${info.number_name || info.number} -> ${numberState}\n`;
    if (numberAttrs) {
      const min = numberAttrs.get ? numberAttrs.get('min') : numberAttrs.min;
      const max = numberAttrs.get ? numberAttrs.get('max') : numberAttrs.max;
      const step = numberAttrs.get ? numberAttrs.get('step') : numberAttrs.step;
      html += `Number attrs: min=${min} max=${max} step=${step}\n`;
    }
  } else {
    html += `Number: (not found)\n`;
  }
  resultEl.textContent = html;
  // update UI elements (we keep buttons outside)
  // set up number input UI dynamically (simple prompt or input)
  // We'll show a prompt when clicking Set Number
}

async function sendAction(action) {
  const node = selectEl.value;
  if (!node) {
    resultEl.textContent = 'Please select a node.';
    return;
  }
  resultEl.textContent = 'Sending...';
  try {
    const url = apiUrl('api/action');
    const resp = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({node, action})
    });
    const data = await resp.json();
    resultEl.textContent = 'Result: ' + JSON.stringify(data);
    await loadNodes(); // refresh states
  } catch (err) {
    console.error(err);
    resultEl.textContent = 'Action failed: ' + (err.message || err);
  }
}

async function setNumberValue() {
  const node = selectEl.value;
  if (!node) {
    resultEl.textContent = 'Please select a node.';
    return;
  }
  // ask user for value
  const raw = prompt('Enter numeric value to set for selected node:');
  if (raw === null) return; // cancelled
  const v = Number(raw);
  if (Number.isNaN(v)) {
    resultEl.textContent = 'Invalid number input';
    return;
  }
  resultEl.textContent = 'Sending number...';
  try {
    const url = apiUrl('api/set_number');
    const resp = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({node, value: v})
    });
    const data = await resp.json();
    resultEl.textContent = 'Number set result: ' + JSON.stringify(data);
    await loadNodes();
  } catch (err) {
    console.error(err);
    resultEl.textContent = 'Set number failed: ' + (err.message || err);
  }
}

document.getElementById('btn-on').addEventListener('click', () => sendAction('on'));
document.getElementById('btn-off').addEventListener('click', () => sendAction('off'));
document.getElementById('btn-toggle').addEventListener('click', () => sendAction('toggle'));

// add a set-number button to call prompt
const setNumberBtn = document.createElement('button');
setNumberBtn.textContent = 'Set Number';
setNumberBtn.addEventListener('click', setNumberValue);
document.body.insertBefore(setNumberBtn, resultEl);

refreshBtn.addEventListener('click', () => loadNodes());
loadNodes();
