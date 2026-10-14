const app = document.querySelector('#app');
const toastRegion = document.querySelector('#toast-region');

const state = {
  session: null,
  csrf: null,
  demo: false,
  dashboard: null,
  selectedId: null,
  selectedIds: new Set(),
  filter: '',
  activeView: 'accounts',
  detailDirty: false,
  groups: [],
  groupsFor: null,
  pollAbort: null,
  pollTimer: null,
  toolOperation: 'qa',
  toolOutput: '',
  toolOutputDemo: false,
  config: null,
  dialog: null,
};

const ICON = {
  menu: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-linecap="round"/></svg>',
  accounts: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="9" cy="8" r="3.25" stroke="currentColor"/><path d="M2.8 20c.7-3.2 2.8-4.8 6.2-4.8s5.5 1.6 6.2 4.8M17 9.5h4M19 7.5v4" stroke="currentColor" stroke-linecap="round"/></svg>',
  tools: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m14.5 5.5 4 4m-7.8 7.8L5 23l-4-4 5.7-5.7M13.1 6.9 16.9 3l4.1 4.1-3.9 3.8M7.5 3.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  logs: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 3.5h14v17H5zM8 8h8M8 12h8M8 16h4" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  settings: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="3" stroke="currentColor"/><path d="M19 12a7.6 7.6 0 0 0-.1-1.2l2-1.5-2-3.4-2.4 1a8 8 0 0 0-2.1-1.2L14.1 3h-4l-.4 2.7a8 8 0 0 0-2.1 1.2l-2.4-1-2 3.4 2 1.5a7.6 7.6 0 0 0 0 2.4l-2 1.5 2 3.4 2.4-1a8 8 0 0 0 2.1 1.2l.4 2.7h4l.4-2.7a8 8 0 0 0 2.1-1.2l2.4 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2Z" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-linecap="round"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="10.7" cy="10.7" r="5.7" stroke="currentColor"/><path d="m15 15 4.2 4.2" stroke="currentColor" stroke-linecap="round"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M20 11a8 8 0 1 0 1 4M20 5v6h-6" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  link: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10 13.8a4.5 4.5 0 0 0 6.4.1l2-2a4.5 4.5 0 0 0-6.4-6.4l-1.1 1.1M14 10.2a4.5 4.5 0 0 0-6.4-.1l-2 2a4.5 4.5 0 0 0 6.4 6.4l1.1-1.1" stroke="currentColor" stroke-linecap="round"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m8 5 11 7-11 7V5Z" stroke="currentColor" stroke-linejoin="round"/></svg>',
  stop: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1" stroke="currentColor"/></svg>',
  eye: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M2.8 12s3.2-5.3 9.2-5.3 9.2 5.3 9.2 5.3-3.2 5.3-9.2 5.3S2.8 12 2.8 12Z" stroke="currentColor"/><circle cx="12" cy="12" r="2.3" stroke="currentColor"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor"/><path d="M12 11v5M12 8h.01" stroke="currentColor" stroke-linecap="round"/></svg>',
  alert: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3.5 21 20H3l9-16.5Z" stroke="currentColor" stroke-linejoin="round"/><path d="M12 9v4M12 16h.01" stroke="currentColor" stroke-linecap="round"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" stroke="currentColor" stroke-linecap="round"/></svg>',
  logout: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m5 12.5 4.2 4.2L19 7" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};
const icon = (name) => ICON[name] || ICON.info;
const stateLabels = { offline: '未连接', code: '待验证码', password: '需二步验证', ready: '已就绪', running: '运行中', error: '连接异常' };
const validStates = new Set(Object.keys(stateLabels));

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
function empty(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function accountName(account) { return String(account?.name || account?.username || account?.phone_masked || '未命名账号'); }
function safeState(account) { return validStates.has(account?.state) ? account.state : 'offline'; }
function isEditableTarget() { const target = document.activeElement; return target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName); }
function responseMessage(data, fallback) { return String(data?.message || data?.detail || data?.error || fallback); }
function formValue(id) { return document.getElementById(id)?.value?.trim() || ''; }
function setText(id, value) { const node = document.getElementById(id); if (node) node.textContent = value === undefined || value === null ? '—' : String(value); }
function setVisible(id, show) { const node = document.getElementById(id); if (node) node.hidden = !show; }
function formatTime(value) {
  if (!value) return '—';
  const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
}
function toast(message, type = 'info') {
  const node = element('div', `toast ${type}`);
  node.insertAdjacentHTML('afterbegin', type === 'error' ? icon('alert') : type === 'success' ? icon('check') : icon('info'));
  const copy = element('div', '', message);
  node.append(copy);
  toastRegion.append(node);
  window.setTimeout(() => node.remove(), 4300);
}

async function api(path, { method = 'GET', body, signal, login = false } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (!login && (method === 'POST' || method === 'PATCH')) {
    if (!state.csrf) throw new Error('安全令牌已失效，请重新登录。');
    headers['X-CSRF-Token'] = state.csrf;
  }
  let response;
  try {
    response = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('无法连接到控制台服务，请检查本机服务状态。');
  }
  let data = null;
  try { data = await response.json(); } catch { /* safe generic error below */ }
  if (!response.ok) {
    if (response.status === 401 && !login) handleSessionExpired();
    throw new Error(responseMessage(data, `请求失败（${response.status}）`));
  }
  return data || {};
}

function handleSessionExpired() {
  stopPolling();
  state.csrf = null;
  state.dashboard = null;
  state.selectedId = null;
  state.selectedIds.clear();
  mountLogin(state.demo);
  toast('会话已结束，请重新登录。', 'error');
}

async function bootstrap() {
  let session;
  try {
    const response = await fetch('/api/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    session = await response.json();
  } catch {
    mountLogin(false, '无法验证控制台会话。请确认服务已启动。');
    return;
  }
  state.session = session || {};
  state.demo = Boolean(session?.demo);
  if (!session?.authenticated) {
    mountLogin(state.demo);
    return;
  }
  state.csrf = session.csrf || null;
  mountConsole();
  await refreshDashboard({ initial: true });
  startPolling();
}

function mountLogin(isDemo, initialError = '') {
  stopPolling();
  app.innerHTML = `
    <section class="login-view">
      <aside class="login-aside">
        <div class="login-brand"><span class="brand-mark">A</span><span>TG Atelier</span></div>
        <div><h1>每个账号，<br>各有分工。</h1><p>集中管理普通 Telegram 账号的登录、群组白名单与 AI 工作流。首次登录始终遵循 Telegram 的验证码与两步验证流程。</p></div>
        <div class="login-foot">私有控制台 · 同源安全会话</div>
      </aside>
      <section class="login-main">
        <div class="login-card">
          <p class="eyebrow">Administrator access</p>
          <h2>进入控制台</h2>
          <p>使用已在本机设置的管理员密码登录。凭据不会存储在浏览器中。</p>
          <form id="login-form" class="login-form" novalidate>
            <div class="field"><label for="login-password">管理员密码</label><input id="login-password" name="password" type="password" autocomplete="current-password" required placeholder="输入管理员密码"></div>
            <p id="demo-login-hint" class="demo-hint"></p>
            <p id="login-error" class="login-error"></p>
            <button class="btn btn-primary" type="submit">安全登录</button>
          </form>
        </div>
      </section>
    </section>`;
  const demoHint = document.querySelector('#demo-login-hint');
  if (isDemo) {
    demoHint.classList.add('is-visible');
    demoHint.append('演示模式密码：', element('strong', '', 'atelier-demo-2026'), '。演示环境不会连接 Telegram 或保存真实密钥。');
  }
  document.querySelector('#login-error').textContent = initialError;
  document.querySelector('#login-form').addEventListener('submit', login);
  document.querySelector('#login-password').focus();
}

async function login(event) {
  event.preventDefault();
  const password = document.querySelector('#login-password').value;
  const errorNode = document.querySelector('#login-error');
  const button = event.currentTarget.querySelector('button[type="submit"]');
  errorNode.textContent = '';
  if (!password) { errorNode.textContent = '请输入管理员密码。'; return; }
  button.disabled = true;
  try {
    const result = await api('/api/login', { method: 'POST', body: { password }, login: true });
    if (!result.csrf) throw new Error('服务未返回安全令牌，请重新登录。');
    state.csrf = result.csrf;
    state.session = { authenticated: true, demo: state.demo };
    mountConsole();
    await refreshDashboard({ initial: true });
    startPolling();
    toast('登录成功。', 'success');
  } catch (error) {
    errorNode.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function mountConsole() {
  app.innerHTML = `
    <div class="console">
      <aside id="sidebar" class="sidebar" aria-label="主导航">
        <div class="brand"><span class="brand-mark">A</span><span>TG Atelier</span></div>
        <p class="nav-group-label">控制台</p>
        <nav class="nav">
          <button class="nav-button active" data-view="accounts" type="button">${icon('accounts')}<span>账号中心</span></button>
          <button class="nav-button" data-view="tools" type="button">${icon('tools')}<span>AI 工作台</span></button>
          <button class="nav-button" data-view="logs" type="button">${icon('logs')}<span>运行记录</span></button>
        </nav>
        <p class="nav-group-label">管理</p>
        <nav class="nav"><button class="nav-button" data-view="config" type="button">${icon('settings')}<span>系统配置</span></button></nav>
        <div class="side-status"><strong>PRIVATE CONSOLE</strong><span>先验证，再上线。<br>凭据仅保留于受限主机。</span></div>
      </aside>
      <main class="main">
        <header class="topbar">
          <div class="topbar-left"><button id="menu-toggle" class="icon-button menu-toggle" type="button" aria-label="打开导航">${icon('menu')}</button><span class="breadcrumb">控制台 / <strong id="breadcrumb-title">账号中心</strong></span></div>
          <div class="topbar-right"><span id="environment" class="environment"><i class="environment-dot"></i><span id="environment-text">安全会话</span></span><span class="admin-name">管理员</span><button id="logout" class="btn btn-quiet" type="button">${icon('logout')}退出</button></div>
        </header>
        <div id="demo-banner" class="demo-banner">${icon('alert')}<span><strong>演示环境。</strong> 账号、事件和工具结果均为示例；不会连接 Telegram 或写入真实密钥。</span></div>
        <section class="content">
          <section id="view-accounts" class="view active">
            <header class="section-head"><div><h1 class="section-title">账号中心</h1><p class="section-subtitle">集中配置会话与分工。首登必须完成验证码和两步验证；已保存会话可一键连接。</p></div><div class="head-actions"><button id="dashboard-refresh" class="btn btn-outline" type="button">${icon('refresh')}刷新</button><button id="add-account" class="btn btn-primary" type="button">${icon('plus')}添加账号</button></div></header>
            <section class="stats" aria-label="真实运行统计">
              <div class="stat"><span class="stat-label">账号总数</span><strong id="stat-total" class="stat-value">—</strong></div>
              <div class="stat"><span class="stat-label">已连接</span><strong id="stat-connected" class="stat-value">—</strong></div>
              <div class="stat"><span class="stat-label">运行中</span><strong id="stat-running" class="stat-value">—</strong></div>
              <div class="stat"><span class="stat-label">白名单群组</span><strong id="stat-groups" class="stat-value">—</strong></div>
              <div class="stat"><span class="stat-label">今日回复</span><strong id="stat-replies" class="stat-value">—</strong></div>
            </section>
            <section class="account-workspace">
              <div class="account-list-pane"><div class="list-toolbar"><label class="search-wrap"><span class="visually-hidden">搜索账号</span>${icon('search')}<input id="account-search" type="search" autocomplete="off" placeholder="搜索名称或账号"></label><div class="list-actions"><span id="selected-count" class="selected-count">已选 0</span><button id="select-all" class="btn btn-quiet" type="button">全选</button><button id="select-none" class="btn btn-quiet" type="button">清除</button></div><div class="list-actions"><button class="btn btn-outline batch-action" data-action="connect" type="button">连接</button><button class="btn btn-outline batch-action" data-action="start" type="button">启动</button><button class="btn btn-outline batch-action" data-action="stop" type="button">停止</button></div></div><div id="account-list" class="account-list"></div></div>
              <div id="detail-pane" class="detail-pane"><div id="account-detail" class="detail-empty"></div></div>
            </section>
          </section>
          <section id="view-tools" class="view"><header class="section-head"><div><h1 class="section-title">AI 工作台</h1><p class="section-subtitle">问答、摘要、翻译与润色只生成受保护草稿，绝不会从这里发送到群组。</p></div></header><section class="workbench"><form id="tool-form" class="tool-form" novalidate><div id="tool-operations" class="segmented" aria-label="选择 AI 功能"><button data-operation="qa" class="active" type="button">问答</button><button data-operation="summary" type="button">摘要</button><button data-operation="translate" type="button">翻译</button><button data-operation="rewrite" type="button">润色</button></div><div class="tool-options"><div class="field"><label for="tool-account">使用账号</label><select id="tool-account" required></select></div><div class="field"><label for="tool-language">输出语言</label><select id="tool-language"><option value="zh-CN">简体中文</option><option value="en">English</option><option value="ja">日本語</option><option value="auto">保持原语言</option></select></div></div><div id="tool-group-field" class="field" hidden><label for="tool-group">摘要群组白名单（可选）</label><select id="tool-group"></select><p class="field-note">仅能选择该账号已保存的白名单群组。</p></div><div class="field"><label for="tool-text">输入内容</label><textarea id="tool-text" required placeholder="输入需要处理的文本；内容仅用于本次草稿请求。"></textarea></div><button id="tool-submit" class="btn btn-primary tool-submit" type="submit">生成草稿</button></form><div class="tool-output"><div class="output-title"><h3>草稿输出</h3><span id="output-tag" class="draft-tag">未生成</span></div><pre id="tool-output" class="output-text output-placeholder">选择账号与功能，输入内容后生成草稿。</pre><div class="output-meta">草稿不会自动发送，也不会写入 Telegram 群组。</div></div></section></section>
          <section id="view-logs" class="view"><header class="section-head"><div><h1 class="section-title">运行记录</h1><p class="section-subtitle">仅显示结构化运行事件，不展示验证码、密钥或群聊内容。</p></div><div class="head-actions"><button id="logs-refresh" class="btn btn-outline" type="button">${icon('refresh')}刷新</button></div></header><section class="event-table"><div class="event-head"><span>时间</span><span>账号</span><span>事件</span><span>状态说明</span></div><div id="event-list"></div></section></section>
          <section id="view-config" class="view"><header class="section-head"><div><h1 class="section-title">系统配置</h1><p class="section-subtitle">密钥从不回显。已配置的密钥字段留空即可保持不变。</p></div></header><section class="config-layout"><div class="config-intro">Telegram API 与 AI 服务凭据仅保存在本机受限目录。首次账号登录仍需使用 Telegram 正常验证码与两步验证。</div><form id="config-form" class="config-form" novalidate><div class="form-section"><h3>Telegram 应用</h3><div class="fields-grid"><div class="field"><label for="config-api-id">API ID</label><input id="config-api-id" type="number" min="0" inputmode="numeric" placeholder="未配置"></div><div class="field"><label for="config-api-hash">API Hash <span id="api-hash-state" class="secret-state unset">未配置</span></label><input id="config-api-hash" type="password" autocomplete="new-password" placeholder="留空保持不变"><p class="field-note">不会回显已保存值。</p></div></div></div><div class="form-section"><h3>AI 服务</h3><div class="fields-grid"><div class="field wide"><label for="config-ai-base">服务地址</label><input id="config-ai-base" type="url" autocomplete="url" placeholder="https://…"></div><div class="field"><label for="config-ai-model">默认模型</label><input id="config-ai-model" type="text" autocomplete="off" placeholder="模型名称"></div><div class="field"><label for="config-ai-token">Token 参数</label><input id="config-ai-token" type="text" autocomplete="off" placeholder="max_completion_tokens"></div><div class="field wide"><label for="config-ai-key">AI Key <span id="ai-key-state" class="secret-state unset">未配置</span></label><input id="config-ai-key" type="password" autocomplete="new-password" placeholder="留空保持不变"><p class="field-note">不会回显已保存值。</p></div><div class="field wide"><label for="config-ai-extra">额外 JSON 参数</label><textarea id="config-ai-extra" spellcheck="false" placeholder="{}"></textarea></div></div></div></form><div class="config-actions"><button id="config-save" class="btn btn-primary" type="button">保存配置</button></div></section></section>
        </section>
      </main>
    </div>
    <div id="dialog-backdrop" class="dialog-backdrop" role="presentation"><section id="dialog" class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title"></section></div>`;
  setupConsoleEvents();
  updateEnvironment();
}

function setupConsoleEvents() {
  document.querySelectorAll('.nav-button').forEach((button) => button.addEventListener('click', () => activateView(button.dataset.view)));
  document.querySelector('#menu-toggle').addEventListener('click', () => document.querySelector('#sidebar').classList.toggle('open'));
  document.querySelector('#logout').addEventListener('click', logout);
  document.querySelector('#dashboard-refresh').addEventListener('click', () => refreshDashboard({ manual: true }));
  document.querySelector('#logs-refresh').addEventListener('click', () => refreshDashboard({ manual: true }));
  document.querySelector('#add-account').addEventListener('click', openAddWizard);
  document.querySelector('#account-search').addEventListener('input', (event) => { state.filter = event.target.value; renderAccountList(); });
  document.querySelector('#select-all').addEventListener('click', selectAllVisible);
  document.querySelector('#select-none').addEventListener('click', () => { state.selectedIds.clear(); renderAccountList(); });
  document.querySelectorAll('.batch-action').forEach((button) => button.addEventListener('click', () => batchAction(button.dataset.action)));
  document.querySelector('#tool-form').addEventListener('submit', submitTool);
  document.querySelectorAll('#tool-operations button').forEach((button) => button.addEventListener('click', () => setToolOperation(button.dataset.operation)));
  document.querySelector('#tool-account').addEventListener('change', renderToolGroups);
  document.querySelector('#config-save').addEventListener('click', saveConfig);
  const backdrop = document.querySelector('#dialog-backdrop');
  backdrop.addEventListener('click', (event) => { if (event.target === backdrop) closeDialog(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') { closeDialog(); document.querySelector('#sidebar')?.classList.remove('open'); } });
}

function updateEnvironment() {
  const environment = document.querySelector('#environment');
  const label = document.querySelector('#environment-text');
  const banner = document.querySelector('#demo-banner');
  if (!environment || !label) return;
  environment.classList.toggle('demo', state.demo);
  environment.classList.toggle('live', !state.demo);
  label.textContent = state.demo ? '演示环境' : '私有环境';
  banner.classList.toggle('is-visible', state.demo);
}

function activateView(view) {
  if (!['accounts', 'tools', 'logs', 'config'].includes(view)) return;
  state.activeView = view;
  state.detailDirty = false;
  document.querySelectorAll('.nav-button').forEach((node) => node.classList.toggle('active', node.dataset.view === view));
  document.querySelectorAll('.view').forEach((node) => node.classList.toggle('active', node.id === `view-${view}`));
  const headings = { accounts: '账号中心', tools: 'AI 工作台', logs: '运行记录', config: '系统配置' };
  setText('breadcrumb-title', headings[view]);
  document.querySelector('#sidebar')?.classList.remove('open');
  if (view === 'config') loadConfig();
  if (view === 'tools') renderToolAccounts();
  if (view === 'logs') renderEvents();
}

async function logout() {
  const button = document.querySelector('#logout');
  button.disabled = true;
  try {
    await api('/api/logout', { method: 'POST', body: {} });
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    state.csrf = null;
    state.dashboard = null;
    state.selectedId = null;
    state.selectedIds.clear();
    stopPolling();
    mountLogin(state.demo);
  }
}

function stopPolling() {
  if (state.pollTimer) window.clearInterval(state.pollTimer);
  state.pollTimer = null;
  if (state.pollAbort) state.pollAbort.abort();
  state.pollAbort = null;
}
function startPolling() {
  stopPolling();
  state.pollTimer = window.setInterval(() => refreshDashboard({ poll: true }), 4000);
}

async function refreshDashboard({ initial = false, manual = false, poll = false } = {}) {
  if (!state.csrf) return;
  if (state.pollAbort) state.pollAbort.abort();
  const controller = new AbortController();
  state.pollAbort = controller;
  try {
    const data = await api('/api/dashboard', { signal: controller.signal });
    if (state.pollAbort !== controller) return;
    renderDashboard(data, { preserveDetail: poll || (!initial && state.detailDirty) });
    if (manual) toast('统计与账号状态已刷新。', 'success');
  } catch (error) {
    if (error.name !== 'AbortError') toast(error.message, 'error');
  } finally {
    if (state.pollAbort === controller) state.pollAbort = null;
  }
}

function renderDashboard(data, { preserveDetail = false } = {}) {
  const accounts = Array.isArray(data?.accounts) ? data.accounts : [];
  const existing = new Set(accounts.map((account) => String(account.id)));
  state.selectedIds = new Set([...state.selectedIds].filter((id) => existing.has(String(id))));
  if (state.selectedId && !existing.has(String(state.selectedId))) {
    state.selectedId = null;
    state.detailDirty = false;
    state.groups = [];
    state.groupsFor = null;
  }
  state.dashboard = { ...data, accounts };
  state.demo = Boolean(data?.demo ?? state.demo);
  updateEnvironment();
  const stats = data?.stats || {};
  const stat = (name) => Object.prototype.hasOwnProperty.call(stats, name) ? stats[name] : '—';
  setText('stat-total', stat('total'));
  setText('stat-connected', stat('connected'));
  setText('stat-running', stat('running'));
  setText('stat-groups', stat('groups'));
  setText('stat-replies', stat('replies_today'));
  renderAccountList();
  renderEvents();
  renderToolAccounts();
  if (!preserveDetail && !state.detailDirty) renderDetail();
}

function accountById(id = state.selectedId) { return state.dashboard?.accounts?.find((account) => String(account.id) === String(id)) || null; }

function renderAccountList() {
  const root = document.querySelector('#account-list');
  const count = document.querySelector('#selected-count');
  if (!root || !state.dashboard) return;
  empty(root);
  const term = state.filter.trim().toLocaleLowerCase();
  const accounts = state.dashboard.accounts.filter((account) => !term || [accountName(account), account.phone_masked, account.username].some((value) => String(value || '').toLocaleLowerCase().includes(term)));
  count.textContent = `已选 ${state.selectedIds.size}`;
  if (!state.dashboard.accounts.length) {
    root.append(emptyState('尚未配置账号', '添加一个普通 Telegram 账号后，按验证码和两步验证步骤完成登录。', '添加账号', openAddWizard));
    return;
  }
  if (!accounts.length) {
    root.append(emptyState('没有匹配账号', '尝试修改搜索条件，或清除当前搜索。'));
    return;
  }
  accounts.forEach((account) => {
    const row = element('button', `account-row${String(account.id) === String(state.selectedId) ? ' active' : ''}`);
    row.type = 'button';
    const check = element('input');
    check.type = 'checkbox';
    check.checked = state.selectedIds.has(String(account.id));
    check.setAttribute('aria-label', `选择 ${accountName(account)}`);
    check.addEventListener('click', (event) => event.stopPropagation());
    check.addEventListener('change', () => {
      const id = String(account.id);
      if (check.checked) state.selectedIds.add(id); else state.selectedIds.delete(id);
      renderAccountList();
    });
    const identity = element('span', 'account-ident');
    identity.append(element('span', 'account-name', accountName(account)), element('span', 'account-phone', account.phone_masked || account.username || '账号未验证'));
    const status = statusPip(account);
    row.append(check, identity, status);
    row.addEventListener('click', () => selectAccount(account.id));
    root.append(row);
  });
}

function emptyState(title, copy, actionLabel, action) {
  const root = element('div', 'account-empty');
  const content = element('div', 'empty-content');
  const visual = element('div', 'empty-icon');
  visual.insertAdjacentHTML('afterbegin', icon('accounts'));
  content.append(visual, element('h3', '', title), element('p', '', copy));
  if (actionLabel && action) {
    const button = element('button', 'btn btn-primary', actionLabel);
    button.type = 'button';
    button.addEventListener('click', action);
    content.append(button);
  }
  root.append(content);
  return root;
}

function statusPip(account) {
  const current = safeState(account);
  const node = element('span', `status-pip ${current}`, stateLabels[current]);
  if (account?.error) node.title = String(account.error);
  return node;
}

function selectAllVisible() {
  const term = state.filter.trim().toLocaleLowerCase();
  state.dashboard?.accounts?.forEach((account) => {
    const match = !term || [accountName(account), account.phone_masked, account.username].some((value) => String(value || '').toLocaleLowerCase().includes(term));
    if (match) state.selectedIds.add(String(account.id));
  });
  renderAccountList();
}

function selectAccount(id) {
  if (String(id) === String(state.selectedId)) return;
  state.selectedId = String(id);
  state.detailDirty = false;
  state.groups = [];
  state.groupsFor = null;
  renderAccountList();
  renderDetail();
  if (window.matchMedia('(max-width: 840px)').matches) document.querySelector('#detail-pane')?.classList.add('mobile-open');
}

function renderDetail() {
  const root = document.querySelector('#account-detail');
  const pane = document.querySelector('#detail-pane');
  if (!root) return;
  const account = accountById();
  empty(root);
  if (!account) {
    pane?.classList.remove('mobile-open');
    root.className = 'detail-empty';
    root.append(emptyState('选择一个账号', '在左侧选择账号，查看登录状态、群组白名单与 AI 分工配置。'));
    return;
  }
  root.className = '';
  const current = safeState(account);
  root.innerHTML = `
    <header class="detail-header"><div><h3 id="detail-title"></h3><div id="detail-meta" class="detail-meta"></div></div><div class="detail-actions"><button id="detail-close" class="icon-button detail-close" type="button" aria-label="关闭详情">${icon('close')}</button><button id="detail-connect" class="btn btn-outline" type="button">${icon('link')}连接</button><button id="detail-start" class="btn btn-primary" type="button">${icon('play')}启动</button><button id="detail-stop" class="btn btn-danger" type="button">${icon('stop')}停止</button></div></header>
    <form id="account-form" class="detail-body" novalidate>
      <div id="detail-status-notice" class="inline-notice"></div>
      <section class="detail-section"><h4>账号分工</h4><div class="fields-grid"><div class="field"><label for="account-name">显示名称</label><input id="account-name" type="text" maxlength="80" autocomplete="off"></div><div class="field"><label for="account-model">覆盖模型（可选）</label><input id="account-model" type="text" maxlength="160" autocomplete="off" placeholder="留空使用系统默认模型"></div><div class="field wide"><label for="account-persona">AI 人设</label><textarea id="account-persona" maxlength="4000" placeholder="定义此账号的角色与回复语气。"></textarea></div><div class="field wide"><label for="account-faq">FAQ 提示</label><textarea id="account-faq" maxlength="6000" placeholder="输入此账号负责的常见问题与回答原则。"></textarea></div><div class="field wide"><span class="field-label">已启用功能</span><div class="choice-line"><label><input id="feature-chat" type="checkbox" value="chat">群聊 AI</label><label><input id="feature-faq" type="checkbox" value="faq">FAQ 问答</label></div></div></div></section>
      <section class="detail-section"><h4>回复策略</h4><div class="fields-grid"><div class="field"><label for="account-mode">触发模式</label><select id="account-mode"><option value="mentions">仅提及</option><option value="smart">智能判断</option><option value="all">全部消息</option></select></div><div class="field"><label for="account-probability">回复概率（0–1）</label><input id="account-probability" type="number" min="0" max="1" step="0.01" inputmode="decimal"></div><div class="field"><label for="account-cooldown">冷却秒数</label><input id="account-cooldown" type="number" min="0" max="86400" step="1" inputmode="numeric"></div><div class="field"><label for="account-hourly">每小时上限</label><input id="account-hourly" type="number" min="0" max="10000" step="1" inputmode="numeric"></div><div class="field"><label for="account-daily">每日上限</label><input id="account-daily" type="number" min="0" max="100000" step="1" inputmode="numeric"></div><div class="field"><span class="field-label">发送模式</span><label class="switch-line"><input id="account-dry-run" type="checkbox">试运行（只生成草稿）</label></div></div></section>
      <section class="detail-section"><h4>群组白名单</h4><div id="group-notice" class="inline-notice"></div><div class="group-controls"><button id="load-groups" class="btn btn-outline" type="button">加载已加入群组</button></div><div id="group-list" class="group-list"></div></section>
      <section class="detail-section"><h4>当前试运行草稿</h4><div class="group-controls"><button id="load-preview" class="btn btn-outline" type="button">${icon('eye')}查看草稿</button></div><div id="preview-box" class="preview-box">尚未读取草稿。</div></section>
      <div class="detail-footer"><button id="account-save" class="btn btn-primary" type="submit">保存账号设置</button></div>
    </form>`;
  setText('detail-title', accountName(account));
  setText('detail-meta', [account.phone_masked, account.username ? `@${account.username.replace(/^@/, '')}` : '', account.tg_user_id ? `ID ${account.tg_user_id}` : '未完成验证'].filter(Boolean).join(' · '));
  const loginButton = element('button', 'btn btn-outline', current === 'code' || current === 'password' ? '继续验证' : '验证登录');
  loginButton.id = 'detail-login';
  loginButton.type = 'button';
  loginButton.disabled = state.demo || current === 'ready' || current === 'running';
  loginButton.addEventListener('click', () => {
    if (current === 'password') showPasswordStep(account.id, accountName(account));
    else showCodeStep(account.id, accountName(account), current === 'code');
  });
  root.querySelector('.detail-actions').prepend(loginButton);
  const notice = document.querySelector('#detail-status-notice');
  notice.insertAdjacentHTML('afterbegin', current === 'running' ? icon('alert') : icon('info'));
  const statusCopy = current === 'running' ? '账号正在运行。为避免运行配置被部分覆盖，请先停止账号再保存设置；服务端也会拒绝该保存。' : current === 'offline' ? '尚未建立已授权会话。请完成首次 Telegram 验证，或对已有会话使用“连接”。' : current === 'code' ? '等待 Telegram 验证码。验证码仅在本次内存登录步骤中短暂使用。' : current === 'password' ? '该账号需要 Telegram 两步验证密码；该步骤无法绕过。' : account.error ? String(account.error) : '已保存会话可连接；启动前需完成 AI 配置和至少一个群组白名单。';
  notice.append(element('span', '', statusCopy));
  if (current === 'running') notice.classList.add('warn');
  document.querySelector('#account-name').value = account.name || '';
  document.querySelector('#account-model').value = account.model || '';
  document.querySelector('#account-persona').value = account.persona || '';
  document.querySelector('#account-faq').value = account.faq || '';
  document.querySelector('#feature-chat').checked = Array.isArray(account.features) && account.features.includes('chat');
  document.querySelector('#feature-faq').checked = Array.isArray(account.features) && account.features.includes('faq');
  document.querySelector('#account-mode').value = ['mentions', 'smart', 'all'].includes(account.reply_mode) ? account.reply_mode : 'smart';
  document.querySelector('#account-probability').value = account.probability ?? 0.15;
  document.querySelector('#account-cooldown').value = account.cooldown ?? 60;
  document.querySelector('#account-hourly').value = account.hourly_limit ?? 20;
  document.querySelector('#account-daily').value = account.daily_limit ?? 100;
  document.querySelector('#account-dry-run').checked = account.dry_run !== false;
  document.querySelector('#account-name').maxLength = 60;
  document.querySelector('#account-model').maxLength = 100;
  document.querySelector('#account-persona').maxLength = 3000;
  document.querySelector('#account-faq').maxLength = 12000;
  for (const [id, min, max] of [['account-cooldown', 10, 3600], ['account-hourly', 1, 100], ['account-daily', 1, 500]]) {
    document.getElementById(id).min = min;
    document.getElementById(id).max = max;
  }
  updateGroupArea(account);
  document.querySelector('#detail-connect').disabled = !['offline', 'error', 'ready'].includes(current);
  document.querySelector('#detail-start').disabled = current === 'running';
  document.querySelector('#detail-stop').disabled = current === 'offline';
  if (current !== 'running') document.querySelector('#detail-stop').textContent = '断开';
  document.querySelector('#detail-connect').addEventListener('click', () => accountOperation('connect'));
  document.querySelector('#detail-start').addEventListener('click', () => accountOperation('start'));
  document.querySelector('#detail-stop').addEventListener('click', () => accountOperation('stop'));
  document.querySelector('#detail-close').addEventListener('click', () => pane?.classList.remove('mobile-open'));
  document.querySelector('#load-groups').addEventListener('click', loadGroups);
  document.querySelector('#load-preview').addEventListener('click', loadPreview);
  document.querySelector('#account-form').addEventListener('input', () => { state.detailDirty = true; });
  document.querySelector('#account-form').addEventListener('change', () => { state.detailDirty = true; });
  document.querySelector('#account-form').addEventListener('submit', saveAccount);
}

function updateGroupArea(account) {
  const notice = document.querySelector('#group-notice');
  const list = document.querySelector('#group-list');
  if (!notice || !list) return;
  empty(notice); empty(list);
  const authorized = ['ready', 'running'].includes(safeState(account));
  notice.insertAdjacentHTML('afterbegin', icon(authorized ? 'info' : 'alert'));
  notice.append(element('span', '', authorized ? '群组数据只会从已完成登录的账号加载。勾选后将作为此账号的自动回复白名单。' : '账号尚未完成登录，暂不能读取已加入的群组。先完成验证或连接保存的会话。'));
  document.querySelector('#load-groups').disabled = !authorized;
  if (state.groupsFor === String(account.id) && state.groups.length) {
    const selected = new Set((account.groups || []).map(String));
    state.groups.forEach((group) => {
      const row = element('label', 'group-row');
      const checkbox = element('input'); checkbox.type = 'checkbox'; checkbox.value = String(group.id); checkbox.checked = selected.has(String(group.id));
      row.append(checkbox, element('span', '', group.title || `群组 ${group.id}`));
      list.append(row);
    });
  } else if (state.groupsFor === String(account.id)) {
    list.append(element('p', 'field-note', '没有可选择的已加入群组。'));
  } else if (Array.isArray(account.groups) && account.groups.length) {
    list.append(element('p', 'field-note', `已保存 ${account.groups.length} 个白名单群组。加载群组后可调整选择。`));
  }
}

function numberField(id, label, { min = 0, max = Number.MAX_SAFE_INTEGER, fractional = false } = {}) {
  const value = Number(document.querySelector(id)?.value);
  if (!Number.isFinite(value) || value < min || value > max || (!fractional && !Number.isInteger(value))) throw new Error(`${label}需为 ${min}–${max} 范围内的${fractional ? '数字' : '整数'}。`);
  return value;
}

async function saveAccount(event) {
  event.preventDefault();
  const account = accountById();
  if (!account) return;
  if (safeState(account) === 'running') { toast('请先停止运行中的账号，再保存设置。', 'error'); return; }
  const button = document.querySelector('#account-save');
  try {
    const features = [];
    if (document.querySelector('#feature-chat').checked) features.push('chat');
    if (document.querySelector('#feature-faq').checked) features.push('faq');
    const payload = {
      name: formValue('account-name'), persona: document.querySelector('#account-persona').value, faq: document.querySelector('#account-faq').value,
      features, reply_mode: document.querySelector('#account-mode').value,
      probability: numberField('#account-probability', '回复概率', { min: 0, max: 1, fractional: true }),
      cooldown: numberField('#account-cooldown', '冷却秒数', { min: 10, max: 3600 }),
      hourly_limit: numberField('#account-hourly', '每小时上限', { min: 1, max: 100 }),
      daily_limit: numberField('#account-daily', '每日上限', { min: 1, max: 500 }),
      dry_run: document.querySelector('#account-dry-run').checked, model: formValue('account-model'),
    };
    if (state.groupsFor === String(account.id)) payload.groups = [...document.querySelectorAll('#group-list input[type="checkbox"]:checked')].map((node) => Number(node.value));
    else payload.groups = Array.isArray(account.groups) ? account.groups : [];
    button.disabled = true;
    await api(`/api/accounts/${encodeURIComponent(account.id)}`, { method: 'PATCH', body: payload });
    state.detailDirty = false;
    toast('账号设置已保存。', 'success');
    await refreshDashboard();
    renderDetail();
  } catch (error) { toast(error.message, 'error'); }
  finally { button.disabled = false; }
}

async function accountOperation(action) {
  const account = accountById();
  if (!account) return;
  const button = document.querySelector(`#detail-${action}`);
  if (button) button.disabled = true;
  try {
    const result = await api(`/api/accounts/${encodeURIComponent(account.id)}/${action}`, { method: 'POST', body: {} });
    toast(responseMessage(result, '账号状态已更新。'), 'success');
    state.detailDirty = false;
    await refreshDashboard();
    renderDetail();
  } catch (error) { toast(error.message, 'error'); }
  finally { if (button) button.disabled = false; }
}

async function batchAction(action) {
  const ids = [...state.selectedIds];
  if (!ids.length) { toast('请先从账号列表多选至少一个账号。', 'error'); return; }
  const button = document.querySelector(`.batch-action[data-action="${action}"]`);
  if (button) button.disabled = true;
  try {
    const result = await api('/api/batch', { method: 'POST', body: { action, ids } });
    const rows = Array.isArray(result.results) ? result.results : [];
    const ok = rows.filter((row) => row.ok).length;
    const failed = rows.length - ok;
    toast(`批量${{ connect: '连接', start: '启动', stop: '停止' }[action]}完成：${ok} 成功${failed ? `，${failed} 需处理` : ''}。`, failed ? 'info' : 'success');
    state.detailDirty = false;
    await refreshDashboard();
    if (state.selectedId) renderDetail();
  } catch (error) { toast(error.message, 'error'); }
  finally { if (button) button.disabled = false; }
}

async function loadGroups() {
  const account = accountById();
  if (!account) return;
  const button = document.querySelector('#load-groups');
  button.disabled = true;
  try {
    const result = await api(`/api/accounts/${encodeURIComponent(account.id)}/groups`);
    state.groups = Array.isArray(result.groups) ? result.groups : [];
    state.groupsFor = String(account.id);
    updateGroupArea(account);
    toast(`已加载 ${state.groups.length} 个群组。`, 'success');
  } catch (error) { toast(error.message, 'error'); }
  finally { button.disabled = false; }
}

async function loadPreview() {
  const account = accountById();
  const box = document.querySelector('#preview-box');
  if (!account || !box) return;
  box.textContent = '正在读取受保护草稿…';
  try {
    const result = await api(`/api/accounts/${encodeURIComponent(account.id)}/preview`);
    const preview = result.preview;
    box.textContent = preview?.text ? String(preview.text) : '当前没有可查看的试运行草稿。';
  } catch (error) { box.textContent = '无法读取草稿。'; toast(error.message, 'error'); }
}

function renderToolAccounts() {
  const select = document.querySelector('#tool-account');
  if (!select || !state.dashboard) return;
  const current = select.value || state.selectedId || '';
  empty(select);
  const accounts = state.dashboard.accounts || [];
  if (!accounts.length) {
    const opt = element('option', '', '暂无已配置账号'); opt.value = ''; select.append(opt); select.disabled = true;
  } else {
    select.disabled = false;
    const first = element('option', '', '选择账号'); first.value = ''; select.append(first);
    accounts.forEach((account) => { const opt = element('option', '', `${accountName(account)} · ${stateLabels[safeState(account)]}`); opt.value = String(account.id); select.append(opt); });
    if ([...select.options].some((opt) => opt.value === String(current))) select.value = String(current);
  }
  renderToolGroups();
}

function setToolOperation(operation) {
  if (!['qa', 'summary', 'translate', 'rewrite'].includes(operation)) return;
  state.toolOperation = operation;
  document.querySelectorAll('#tool-operations button').forEach((node) => node.classList.toggle('active', node.dataset.operation === operation));
  setVisible('tool-group-field', operation === 'summary');
  renderToolGroups();
}

function renderToolGroups() {
  const group = document.querySelector('#tool-group');
  const field = document.querySelector('#tool-group-field');
  const selectedAccount = accountById(document.querySelector('#tool-account')?.value);
  if (!group || !field) return;
  field.hidden = state.toolOperation !== 'summary';
  const previous = group.value;
  empty(group);
  const none = element('option', '', '不指定群组白名单'); none.value = ''; group.append(none);
  const savedGroups = Array.isArray(selectedAccount?.groups) ? selectedAccount.groups : [];
  savedGroups.forEach((id) => { const option = element('option', '', `白名单群组 ${id}`); option.value = String(id); group.append(option); });
  if (savedGroups.some((id) => String(id) === previous)) group.value = previous;
  group.disabled = !selectedAccount || !savedGroups.length;
}

async function submitTool(event) {
  event.preventDefault();
  const account
 = document.querySelector('#tool-account')?.value;
  const text = document.querySelector('#tool-text')?.value || '';
  const submit = document.querySelector('#tool-submit');
  const output = document.querySelector('#tool-output');
  if (!account) { toast('请选择一个账号后再生成草稿。', 'error'); return; }
  if (!text.trim() && !(state.toolOperation === 'summary' && document.querySelector('#tool-group')?.value)) { toast('请输入内容，或为摘要选择一个白名单群。', 'error'); return; }
  const payload = {
    account_id: account,
    operation: state.toolOperation,
    text,
    language: document.querySelector('#tool-language').value,
  };
  if (state.toolOperation === 'summary') {
    const groupId = document.querySelector('#tool-group')?.value;
    if (groupId) payload.group_id = groupId;
  }
  submit.disabled = true;
  output.classList.remove('output-placeholder');
  output.textContent = '正在生成草稿…';
  setText('output-tag', '草稿生成中');
  try {
    const result = await api('/api/tools', { method: 'POST', body: payload });
    state.toolOutput = String(result.text || '服务未返回草稿内容。');
    state.toolOutputDemo = Boolean(result.demo);
    output.textContent = state.toolOutput;
    setText('output-tag', result.demo ? '草稿 · 演示' : '仅草稿 · 不发送');
  } catch (error) {
    output.textContent = '草稿生成失败。';
    setText('output-tag', '未生成');
    toast(error.message, 'error');
  } finally { submit.disabled = false; }
}

function renderEvents() {
  const root = document.querySelector('#event-list');
  if (!root || !state.dashboard) return;
  empty(root);
  const events = Array.isArray(state.dashboard.events) ? state.dashboard.events : [];
  if (!events.length) {
    const row = element('div', 'simple-empty', '尚无结构化运行事件。完成配置或执行账号操作后将在此显示安全状态记录。');
    root.append(row);
    return;
  }
  events.forEach((event) => {
    const row = element('div', 'event-row');
    const account = accountById(event.account_id);
    const eventTime = element('time', '', formatTime(event.created_at || event.time || event.at));
    const who = element('span', '', account ? accountName(account) : (event.account_name || '系统'));
    const kind = element('span', 'event-kind', event.kind || 'EVENT');
    const message = element('span', '', event.message || '已记录安全状态事件。');
    row.append(eventTime, who, kind, message);
    root.append(row);
  });
}

async function loadConfig() {
  const form = document.querySelector('#config-form');
  if (!form || state.activeView !== 'config') return;
  try {
    const config = await api('/api/config');
    state.config = config;
    document.querySelector('#config-api-id').value = config.api_id || '';
    document.querySelector('#config-ai-base').value = config.ai_base || '';
    document.querySelector('#config-ai-model').value = config.ai_model || '';
    document.querySelector('#config-ai-token').value = config.ai_token_parameter || '';
    document.querySelector('#config-ai-extra').value = config.ai_extra_json || '{}';
    const apiHashState = document.querySelector('#api-hash-state');
    const aiKeyState = document.querySelector('#ai-key-state');
    apiHashState.textContent = config.api_hash_set ? '已配置 · 留空保持' : '未配置';
    aiKeyState.textContent = config.ai_key_set ? '已配置 · 留空保持' : '未配置';
    apiHashState.classList.toggle('unset', !config.api_hash_set);
    aiKeyState.classList.toggle('unset', !config.ai_key_set);
    document.querySelector('#config-api-hash').value = '';
    document.querySelector('#config-ai-key').value = '';
    document.querySelector('#config-api-hash').disabled = state.demo;
    document.querySelector('#config-ai-key').disabled = state.demo;
    if (state.demo) {
      let notice = document.querySelector('#config-demo-notice');
      if (!notice) {
        notice = element('div', 'inline-notice warn'); notice.id = 'config-demo-notice';
        notice.insertAdjacentHTML('afterbegin', icon('alert'));
        notice.append(element('span', '', '演示环境仅可查看系统配置，禁止写入真实凭据。下载后可在本机后台配置。'));
        form.parentElement.insertBefore(notice, form);
      }
      form.querySelectorAll('input, textarea').forEach((node) => { node.disabled = true; });
      document.querySelector('#config-save').disabled = true;
    }
  } catch (error) { toast(error.message, 'error'); }
}

async function saveConfig() {
  const button = document.querySelector('#config-save');
  if (!button) return;
  try {
    const apiId = formValue('config-api-id');
    const extra = document.querySelector('#config-ai-extra').value.trim() || '{}';
    try { JSON.parse(extra); } catch { throw new Error('额外 JSON 参数格式无效。'); }
    const payload = {
      ai_base: formValue('config-ai-base'),
      ai_model: formValue('config-ai-model'),
      ai_token_parameter: formValue('config-ai-token'),
      ai_extra_json: extra,
    };
    if (apiId !== '') {
      payload.api_id = Number(apiId);
      if (!Number.isInteger(payload.api_id) || payload.api_id <= 0) throw new Error('API ID 必须是正整数。');
    }
    const apiHash = document.querySelector('#config-api-hash').value;
    const aiKey = document.querySelector('#config-ai-key').value;
    if (!state.demo && apiHash) payload.api_hash = apiHash;
    if (!state.demo && aiKey) payload.ai_key = aiKey;
    button.disabled = true;
    await api('/api/config', { method: 'PATCH', body: payload });
    toast('系统配置已保存；密钥不会回显。', 'success');
    await loadConfig();
  } catch (error) { toast(error.message, 'error'); }
  finally { button.disabled = false; }
}

function closeDialog() {
  const backdrop = document.querySelector('#dialog-backdrop');
  if (!backdrop) return;
  backdrop.classList.remove('open');
  empty(document.querySelector('#dialog'));
  state.dialog = null;
}

function openDialog(title) {
  const backdrop = document.querySelector('#dialog-backdrop');
  const dialog = document.querySelector('#dialog');
  if (!backdrop || !dialog) return null;
  empty(dialog);
  backdrop.classList.add('open');
  dialog.innerHTML = `<header class="dialog-head"><h2 id="dialog-title"></h2><button id="dialog-close" class="icon-button" type="button" aria-label="关闭">${icon('close')}</button></header><div id="dialog-content"></div>`;
  setText('dialog-title', title);
  document.querySelector('#dialog-close').addEventListener('click', closeDialog);
  state.dialog = dialog;
  return document.querySelector('#dialog-content');
}

function wizardSteps(active) {
  const labels = ['账号', '验证码', '二步验证'];
  const root = element('div', 'wizard-steps');
  labels.forEach((label, index) => {
    const status = index < active ? ' done' : index === active ? ' active' : '';
    root.append(element('span', `wizard-step${status}`, label));
  });
  return root;
}

function openAddWizard() {
  if (state.demo) {
    toast('演示环境禁止新增账号或发起 Telegram 登录。', 'error');
    return;
  }
  const content = openDialog('添加 Telegram 账号');
  if (!content) return;
  content.append(wizardSteps(0));
  const body = element('div', 'dialog-body');
  content.append(body);
  body.append(element('p', '', '使用普通 Telegram 账号。创建后仍需按 Telegram 正常流程接收验证码；若启用了两步验证，也必须输入该密码。'));
  const form = element('form'); form.id = 'add-account-form'; form.noValidate = true;
  const name = element('div', 'field');
  name.append(element('label', '', '显示名称'));
  const nameInput = element('input'); nameInput.id = 'wizard-name'; nameInput.type = 'text'; nameInput.maxLength = 60; nameInput.placeholder = '例如：客服助手 A'; name.append(nameInput);
  const phone = element('div', 'field');
  phone.append(element('label', '', 'Telegram 手机号'));
  const phoneInput = element('input'); phoneInput.id = 'wizard-phone'; phoneInput.type = 'tel'; phoneInput.autocomplete = 'tel'; phoneInput.placeholder = '+8613800000000'; phone.append(phoneInput);
  const error = element('p', 'login-error'); error.id = 'wizard-error';
  form.append(name, phone, error);
  body.append(form);
  const actions = element('div', 'dialog-actions');
  const cancel = element('button', 'btn btn-outline', '取消'); cancel.type = 'button'; cancel.addEventListener('click', closeDialog);
  const next = element('button', 'btn btn-primary', '创建并继续'); next.type = 'submit'; form.append(actions); actions.append(cancel, next);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const displayName = nameInput.value.trim(); const phoneNumber = phoneInput.value.trim();
    error.textContent = '';
    if (!displayName || !phoneNumber) { error.textContent = '请填写显示名称和 Telegram 手机号。'; return; }
    if (!/^\+[1-9][0-9]{7,14}$/.test(phoneNumber)) { error.textContent = '手机号请使用 +国家区号和数字，不含空格或短横线。'; return; }
    next.disabled = true;
    try {
      const result = await api('/api/accounts', { method: 'POST', body: { name: displayName, phone: phoneNumber } });
      const account = result.account;
      if (!account?.id) throw new Error('服务未返回新账号标识。');
      state.selectedId = String(account.id);
      state.selectedIds.add(String(account.id));
      await refreshDashboard();
      showCodeStep(account.id, accountName(account));
    } catch (err) { error.textContent = err.message; }
    finally { next.disabled = false; }
  });
  nameInput.focus();
}

function showCodeStep(id, name, alreadyRequested = false) {
  const content = openDialog('完成 Telegram 登录');
  if (!content) return;
  content.append(wizardSteps(1));
  const body = element('div', 'dialog-body');
  content.append(body);
  body.append(element('p', '', `正在为“${name}”建立会话。验证码只在当前验证步骤的内存中短暂使用，不会保存到控制台。`));
  const status = element('div', 'wizard-state'); status.id = 'wizard-state'; status.insertAdjacentHTML('afterbegin', icon('info'));
  status.append(element('span', '', '先请求验证码。若账号已有授权会话，服务会直接报告已就绪。'));
  const form = element('form'); form.noValidate = true;
  const field = element('div', 'field'); field.style.marginTop = '18px'; field.append(element('label', '', 'Telegram 验证码'));
  const code = element('input'); code.type = 'text'; code.inputMode = 'numeric'; code.autocomplete = 'one-time-code'; code.maxLength = 10; code.placeholder = '收到后输入验证码'; code.disabled = !alreadyRequested; field.append(code); form.append(field);
  body.append(status, form);
  const actions = element('div', 'dialog-actions');
  const cancel = element('button', 'btn btn-outline', '稍后继续'); cancel.type = 'button'; cancel.addEventListener('click', closeDialog);
  const request = element('button', 'btn btn-outline', '请求验证码'); request.type = 'button';
  const verify = element('button', 'btn btn-primary', '验证并继续'); verify.type = 'submit'; verify.disabled = !alreadyRequested;
  actions.append(cancel, request, verify); form.append(actions);
  request.addEventListener('click', async () => {
    request.disabled = true;
    try {
      const result = await api(`/api/accounts/${encodeURIComponent(id)}/code/request`, { method: 'POST', body: {} });
      const message = responseMessage(result, '已请求验证码。');
      empty(status); status.classList.remove('error'); status.insertAdjacentHTML('afterbegin', icon('info')); status.append(element('span', '', message));
      if (result.state === 'ready') { showWizardDone(id, name, message); return; }
      code.disabled = false; verify.disabled = false; code.focus();
    } catch (error) { setWizardError(status, error.message); }
    finally { request.disabled = false; }
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!code.value.trim()) { setWizardError(status, '请输入 Telegram 发送的验证码。'); return; }
    verify.disabled = true;
    try {
      const result = await api(`/api/accounts/${encodeURIComponent(id)}/code/verify`, { method: 'POST', body: { code: code.value.trim() } });
      const message = responseMessage(result, '验证码已验证。');
      if (result.state === 'password') { showPasswordStep(id, name, message); return; }
      if (result.state === 'ready') { showWizardDone(id, name, message); return; }
      setWizardError(status, message);
    } catch (error) { setWizardError(status, error.message); }
    finally { verify.disabled = false; }
  });
}

function showPasswordStep(id, name, initialMessage) {
  const content = openDialog('需要两步验证');
  if (!content) return;
  content.append(wizardSteps(2));
  const body = element('div', 'dialog-body');
  content.append(body);
  body.append(element('p', '', `“${name}”启用了 Telegram 两步验证。此步骤不能绕过；密码仅用于本次验证，不会由控制台持久保存。`));
  const status = element('div', 'wizard-state'); status.insertAdjacentHTML('afterbegin', icon('alert')); status.append(element('span', '', initialMessage || '请输入 Telegram 两步验证密码。'));
  const form = element('form'); form.noValidate = true;
  const field = element('div', 'field'); field.style.marginTop = '18px'; field.append(element('label', '', 'Telegram 两步验证密码'));
  const password = element('input'); password.type = 'password'; password.autocomplete = 'current-password'; password.placeholder = '输入两步验证密码'; field.append(password); form.append(field);
  body.append(status, form);
  const actions = element('div', 'dialog-actions');
  const later = element('button', 'btn btn-outline', '稍后继续'); later.type = 'button'; later.addEventListener('click', closeDialog);
  const verify = element('button', 'btn btn-primary', '验证并完成'); verify.type = 'submit'; actions.append(later, verify); form.append(actions);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!password.value) { setWizardError(status, '请输入 Telegram 两步验证密码。'); return; }
    verify.disabled = true;
    try {
      const result = await api(`/api/accounts/${encodeURIComponent(id)}/password/verify`, { method: 'POST', body: { password: password.value } });
      if (result.state === 'ready') { showWizardDone(id, name, responseMessage(result, '两步验证完成。')); return; }
      setWizardError(status, responseMessage(result, '两步验证尚未完成。'));
    } catch (error) { setWizardError(status, error.message); }
    finally { verify.disabled = false; }
  });
  password.focus();
}

function setWizardError(node, message) {
  empty(node); node.classList.add('error'); node.insertAdjacentHTML('afterbegin', icon('alert')); node.append(element('span', '', message));
}

function showWizardDone(id, name, message) {
  const content = openDialog('账号已验证');
  if (!content) return;
  content.append(wizardSteps(3));
  const body = element('div', 'dialog-body');
  content.append(body);
  body.append(element('p', '', `“${name}”已完成正常 Telegram 登录流程。已保存会话后，可以从账号详情使用“连接”，并在完成配置后启动。`));
  const done = element('div', 'wizard-state'); done.insertAdjacentHTML('afterbegin', icon('check')); done.append(element('span', '', message || '会话已就绪。')); body.append(done);
  const actions = element('div', 'dialog-actions');
  const finish = element('button', 'btn btn-primary', '前往账号设置'); finish.type = 'button'; finish.addEventListener('click', async () => { closeDialog(); state.selectedId = String(id); state.detailDirty = false; await refreshDashboard(); renderDetail(); }); actions.append(finish); body.append(actions);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
} else {
  bootstrap();
}
