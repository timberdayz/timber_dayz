const tokenParam = new URLSearchParams(window.location.search).get('token');
if (tokenParam) {
  window.sessionStorage.setItem('xihong-local-console-token', tokenParam);
  history.replaceState({}, document.title, window.location.pathname);
}

const token = tokenParam || window.sessionStorage.getItem('xihong-local-console-token') || '';
const TOKEN_HEADER = 'X-Local-Console-Token';
const POLL_INTERVAL_MS = 2000;

const STATE_LABELS = {
  stopped: '未运行',
  starting: '启动中',
  running: '运行中',
  stopping: '停止中',
  failed: '启动失败',
  'external-running': '外部运行',
};

const DEFAULT_MESSAGES = {
  stopped: '等待启动',
  starting: '正在执行启动检查',
  running: '服务运行正常',
  stopping: '正在停止受控进程',
  failed: '启动失败，请查看日志',
  'external-running': '检测到控制台外部启动的实例',
};

const ROUTES = {
  'local-collection': {
    start: '/api/services/local-collection/start',
    open: '/api/services/local-collection/open',
    stop: '/api/services/local-collection/stop',
    log: '/api/services/local-collection/log',
  },
  'inspection-panel': {
    start: '/api/services/inspection-panel/start',
    open: '/api/services/inspection-panel/open',
    stop: '/api/services/inspection-panel/stop',
    log: '/api/services/inspection-panel/log',
  },
};

const connection = document.querySelector('.connection');
const connectionLabel = document.querySelector('#connectionLabel');
const globalNotice = document.querySelector('#globalNotice');
const updatedAt = document.querySelector('#updatedAt');
const refreshButton = document.querySelector('#refreshButton');
const stopAllButton = document.querySelector('#stopAllButton');
const logDialog = document.querySelector('#logDialog');
const logTitle = document.querySelector('#logTitle');
const logContent = document.querySelector('#logContent');

async function api(path, options = {}) {
  const response = await window.fetch(path, {
    ...options,
    headers: {
      [TOKEN_HEADER]: token,
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `请求失败 (${response.status})`);
  }
  return payload;
}

function setConnection(online, message) {
  connection.classList.toggle('online', online);
  connection.classList.toggle('offline', !online);
  connectionLabel.textContent = message;
}

function showNotice(message) {
  globalNotice.textContent = message;
  globalNotice.hidden = !message;
}

function renderService(service) {
  const card = document.querySelector(`[data-service="${service.id}"]`);
  if (!card) return;

  const state = service.state || 'stopped';
  const stateBadge = card.querySelector('[data-role="state"]');
  const message = card.querySelector('[data-role="message"]');
  const startButton = card.querySelector('[data-action="start"]');
  const openButton = card.querySelector('[data-action="open"]');
  const stopButton = card.querySelector('[data-action="stop"]');
  const logButton = card.querySelector('[data-action="log"]');

  stateBadge.textContent = STATE_LABELS[state] || state;
  stateBadge.className = `state-badge ${state}`;
  message.textContent = service.last_error || DEFAULT_MESSAGES[state] || '';
  message.classList.toggle('error', state === 'failed');

  startButton.disabled = !['stopped', 'failed'].includes(state);
  openButton.disabled = state !== 'running' || !service.launch_url;
  stopButton.disabled = !service.managed || !['starting', 'running'].includes(state);
  logButton.hidden = !service.log_available && state !== 'failed';
}

async function refreshStatus() {
  if (!token) {
    setConnection(false, '凭据缺失');
    showNotice('请重新双击根目录 local_console.cmd 打开控制台。');
    return;
  }
  try {
    const payload = await api('/api/status');
    payload.services.forEach(renderService);
    updatedAt.textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    setConnection(true, '本机已连接');
    showNotice('');
  } catch (error) {
    setConnection(false, '连接中断');
    showNotice(error.message);
  }
}

async function runServiceAction(serviceId, action, button) {
  const route = ROUTES[serviceId] && ROUTES[serviceId][action];
  if (!route) return;
  button.disabled = true;
  showNotice('');
  try {
    await api(route, { method: 'POST' });
  } catch (error) {
    showNotice(error.message);
  } finally {
    await refreshStatus();
  }
}

async function showLog(serviceId) {
  const route = ROUTES[serviceId] && ROUTES[serviceId].log;
  if (!route) return;
  const card = document.querySelector(`[data-service="${serviceId}"]`);
  try {
    const payload = await api(route);
    logTitle.textContent = `${card.querySelector('h2').textContent}运行日志`;
    logContent.textContent = payload.lines.length ? payload.lines.join('\n') : '暂无日志';
    logDialog.showModal();
  } catch (error) {
    showNotice(error.message);
  }
}

document.querySelectorAll('.service-card').forEach((card) => {
  const serviceId = card.dataset.service;
  card.querySelectorAll('[data-action]').forEach((button) => {
    button.addEventListener('click', () => {
      const action = button.dataset.action;
      if (action === 'log') {
        showLog(serviceId);
      } else {
        runServiceAction(serviceId, action, button);
      }
    });
  });
});

refreshButton.addEventListener('click', refreshStatus);
stopAllButton.addEventListener('click', async () => {
  if (!window.confirm('确认停止本地采集系统和巡店面板？')) return;
  stopAllButton.disabled = true;
  try {
    await api('/api/services/stop-all', { method: 'POST' });
    await refreshStatus();
  } catch (error) {
    showNotice(error.message);
  } finally {
    stopAllButton.disabled = false;
  }
});

document.querySelector('#closeLogButton').addEventListener('click', () => logDialog.close());
logDialog.addEventListener('click', (event) => {
  if (event.target === logDialog) logDialog.close();
});

refreshStatus();
window.setInterval(refreshStatus, POLL_INTERVAL_MS);
