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
  failed: '启动失败，请查看本地控制台窗口',
  'external-running': '检测到控制台外部启动的实例',
};

const ROUTES = {
  'local-collection': {
    start: '/api/services/local-collection/start',
    open: '/api/services/local-collection/open',
    stop: '/api/services/local-collection/stop',
  },
  'inspection-panel': {
    start: '/api/services/inspection-panel/start',
    open: '/api/services/inspection-panel/open',
    stop: '/api/services/inspection-panel/stop',
  },
};

const connection = document.querySelector('.connection');
const connectionLabel = document.querySelector('#connectionLabel');
const globalNotice = document.querySelector('#globalNotice');
const updatedAt = document.querySelector('#updatedAt');
const refreshButton = document.querySelector('#refreshButton');
const stopAllButton = document.querySelector('#stopAllButton');

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
  const diagnostic = card.querySelector('[data-role="diagnostic"]');
  const failureCode = card.querySelector('[data-role="failure-code"]');
  const failureSummary = card.querySelector('[data-role="failure-summary"]');
  const recoveryHint = card.querySelector('[data-role="recovery-hint"]');
  const launchStage = card.querySelector('[data-role="launch-stage"]');
  const lastSuccess = card.querySelector('[data-role="last-success"]');

  stateBadge.textContent = STATE_LABELS[state] || state;
  stateBadge.className = `state-badge ${state}`;
  message.textContent = service.last_failure_summary || service.last_error || DEFAULT_MESSAGES[state] || '';
  message.classList.toggle('error', state === 'failed');
  const hasDiagnostic = Boolean(
    service.failure_code || service.last_failure_summary || service.recovery_hint || service.launch_stage || service.last_success_at
  );
  diagnostic.hidden = !hasDiagnostic;
  failureCode.textContent = service.failure_code ? `故障代码: ${service.failure_code}` : '';
  failureSummary.textContent = service.last_failure_summary || '';
  recoveryHint.textContent = service.recovery_hint ? `恢复建议: ${service.recovery_hint}` : '';
  launchStage.textContent = service.launch_stage ? `启动阶段: ${service.launch_stage}` : '';
  lastSuccess.textContent = service.last_success_at
    ? `最近成功: ${new Date(service.last_success_at * 1000).toLocaleString('zh-CN', { hour12: false })}`
    : '';

  startButton.disabled = !['stopped', 'failed'].includes(state);
  openButton.disabled = state !== 'running' || !service.launch_url;
  stopButton.disabled = !service.managed || !['starting', 'running'].includes(state);
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

document.querySelectorAll('.service-card').forEach((card) => {
  const serviceId = card.dataset.service;
  card.querySelectorAll('[data-action]').forEach((button) => {
    button.addEventListener('click', () => {
      const action = button.dataset.action;
      runServiceAction(serviceId, action, button);
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

refreshStatus();
window.setInterval(refreshStatus, POLL_INTERVAL_MS);
