"use strict";

const $ = (id) => document.getElementById(id);
const view = { csrf: "", name: "", productPage: 1, productTotal: 0, movementPage: 1, movementTotal: 0 };
let toastTimer;

function showScreen(id) {
  for (const name of ["loading-screen", "login-screen", "bind-screen", "dashboard"]) {
    $(name).hidden = name !== id;
  }
  $("logout").hidden = id !== "dashboard" && id !== "bind-screen";
}

function toast(message, error = false) {
  const box = $("toast");
  box.textContent = message;
  box.classList.toggle("error", error);
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, 4600);
}

async function api(path, method = "GET", data) {
  const options = { method, credentials: "same-origin", cache: "no-store", headers: {} };
  if (data !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(data);
  }
  if (method !== "GET" && view.csrf) options.headers["X-CSRF-Token"] = view.csrf;
  let response;
  try { response = await fetch(path, options); }
  catch { throw new Error("网络暂时不可用，请稍后重试。"); }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) showScreen("login-screen");
    throw new Error(result.error || `请求失败（${response.status}）。`);
  }
  return result;
}

function localDay(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit"
  }).formatToParts(date);
  const pick = (key) => parts.find((p) => p.type === key)?.value;
  return `${pick("year")}-${pick("month")}-${pick("day")}`;
}

function numberText(raw) {
  try { return new Intl.NumberFormat("zh-CN").format(BigInt(raw)); }
  catch { return String(raw); }
}

function cell(text, className = "") {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function emptyRow(body, span, text) {
  body.replaceChildren();
  const tr = document.createElement("tr");
  const td = cell(text, "empty-cell");
  td.colSpan = span;
  tr.append(td);
  body.append(tr);
}

async function refreshSession() {
  const result = await api("/admin/api/session");
  if (!result.authenticated) {
    view.csrf = "";
    showScreen("login-screen");
    return false;
  }
  view.csrf = result.csrf;
  view.name = result.name || "管理员";
  if (!result.authorized) {
    $("link-taken").hidden = !result.link_taken;
    $("bind-form").hidden = Boolean(result.link_taken);
    showScreen("bind-screen");
    return false;
  }
  $("account-name").textContent = view.name + " · 已授权";
  showScreen("dashboard");
  return true;
}

async function loadSummary() {
  const data = await api("/admin/api/summary");
  $("sku-count").textContent = numberText(data.sku_count);
  $("total-units").textContent = numberText(data.total_units);
  $("today-in").textContent = "+" + numberText(data.today_in);
  $("today-out").textContent = "−" + numberText(data.today_out);
  $("current-date").textContent = data.local_date;
}

async function loadProducts() {
  const q = $("product-search").value.trim();
  const data = await api(`/admin/api/products?page=${view.productPage}&q=${encodeURIComponent(q)}`);
  view.productTotal = data.total;
  const body = $("product-rows");
  body.replaceChildren();
  if (!data.items.length) emptyRow(body, 3, q ? "没有符合搜索条件的商品。" : "尚无商品，先在右侧记录一笔入库。 ");
  for (const item of data.items) {
    const tr = document.createElement("tr");
    tr.append(cell(item.product_id, "sku-text"), cell(numberText(item.quantity), "number-cell"));
    const actions = document.createElement("td");
    const wrapper = document.createElement("div");
    wrapper.className = "row-actions";
    const edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "调整库存";
    edit.addEventListener("click", () => {
      $("stock-id").value = item.product_id;
      $("stock-id").scrollIntoView({ behavior: "smooth", block: "center" });
      $("stock-quantity").focus();
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger";
    remove.textContent = "删除";
    remove.addEventListener("click", async () => {
      if (!window.confirm(`确定删除商品 ${item.product_id} 吗？商品记录将删除，但出入库流水仍保留。`)) return;
      try {
        const result = await api("/admin/api/products", "DELETE", { product_id: item.product_id });
        toast(result.message);
        view.productPage = 1;
        await Promise.all([loadSummary(), loadProducts(), loadMovements(), loadStats()]);
      } catch (error) { toast(error.message, true); }
    });
    wrapper.append(edit, remove);
    actions.append(wrapper);
    tr.append(actions);
    body.append(tr);
  }
  $("products-count").textContent = `共 ${data.total} 件商品`;
  $("products-page").textContent = `${view.productPage} / ${Math.max(1, Math.ceil(data.total / 25))}`;
  $("products-prev").disabled = view.productPage <= 1;
  $("products-next").disabled = view.productPage * 25 >= data.total;
}

async function loadMovements() {
  const q = $("movement-filter").value.trim();
  const data = await api(`/admin/api/movements?page=${view.movementPage}&product_id=${encodeURIComponent(q)}`);
  view.movementTotal = data.total;
  const body = $("movement-rows");
  body.replaceChildren();
  if (!data.items.length) emptyRow(body, 4, "暂无符合条件的出入库记录。");
  const labels = { in: "入库", out: "出库", delete: "删除" };
  for (const item of data.items) {
    const tr = document.createElement("tr");
    const time = item.occurred_at.replace("T", " ").slice(0, 16);
    tr.append(cell(time), cell(item.product_id, "sku-text"));
    const action = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `action-badge badge-${["in", "out", "delete"].includes(item.action) ? item.action : "delete"}`;
    badge.textContent = labels[item.action] || item.action;
    action.append(badge);
    tr.append(action, cell(numberText(item.quantity), "number-cell"));
    body.append(tr);
  }
  $("movements-count").textContent = `共 ${data.total} 条流水`;
  $("movements-page").textContent = `${view.movementPage} / ${Math.max(1, Math.ceil(data.total / 20))}`;
  $("movements-prev").disabled = view.movementPage <= 1;
  $("movements-next").disabled = view.movementPage * 20 >= data.total;
}

async function loadStats() {
  const start = $("stats-start").value;
  const end = $("stats-end").value;
  if (!start || !end) return;
  const data = await api(`/admin/api/stats?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
  const totalIn = data.days.reduce((sum, row) => sum + BigInt(row.incoming), 0n);
  const totalOut = data.days.reduce((sum, row) => sum + BigInt(row.outgoing), 0n);
  $("stats-summary").textContent = `${data.start} — ${data.end} · 入库 ${numberText(totalIn)} · 出库 ${numberText(totalOut)} · ${data.timezone}`;
  const area = $("stats-list");
  area.replaceChildren();
  const max = Math.max(1, ...data.days.map((row) => Number(BigInt(row.incoming) + BigInt(row.outgoing))));
  for (const row of data.days) {
    const line = document.createElement("div");
    line.className = "stats-row";
    const date = document.createElement("span");
    date.className = "stats-date";
    date.textContent = row.date;
    const track = document.createElement("span");
    track.className = "bar-track";
    const incoming = document.createElement("span");
    incoming.className = "bar-in";
    incoming.style.width = `${(Number(row.incoming) / max) * 100}%`;
    const outgoing = document.createElement("span");
    outgoing.className = "bar-out";
    outgoing.style.width = `${(Number(row.outgoing) / max) * 100}%`;
    track.append(incoming, outgoing);
    const values = document.createElement("span");
    values.className = "stats-values";
    values.textContent = `入 ${numberText(row.incoming)} / 出 ${numberText(row.outgoing)}`;
    line.append(date, track, values);
    area.append(line);
  }
}

async function loadDashboard() {
  const results = await Promise.allSettled([loadSummary(), loadProducts(), loadMovements(), loadStats()]);
  const failure = results.find((item) => item.status === "rejected");
  if (failure) toast(failure.reason.message || "部分数据加载失败，请刷新页面。", true);
}

function setup() {
  const embedded = window.self !== window.top;
  $("iframe-tip").hidden = !embedded;
  if (embedded) {
    $("login-button").disabled = true;
    showScreen("login-screen");
    return;
  }
  $("login-button").addEventListener("click", async () => {
    try {
      const data = await api("/admin/api/oauth/start", "POST", { origin: window.location.origin });
      window.location.assign(data.url);
    } catch (error) { toast(error.message, true); }
  });
  $("generate-bind").addEventListener("click", async () => {
    try {
      const data = await api("/admin/api/bind", "POST", {});
      if (data.authorized) { if (await refreshSession()) await loadDashboard(); return; }
      $("bind-code").textContent = data.command;
      $("bind-code-wrap").hidden = false;
      $("bind-countdown").textContent = "请在 5 分钟内发送至机器人私聊。";
    } catch (error) { toast(error.message, true); }
  });
  $("copy-bind").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("bind-code").textContent); toast("命令已复制，请粘贴到机器人私聊。 "); }
    catch { toast("复制失败，请手动选择命令。", true); }
  });
  $("check-bind").addEventListener("click", async () => {
    try { if (await refreshSession()) { toast("绑定成功，欢迎回来。"); await loadDashboard(); }
      else toast("尚未完成绑定，请确认由机器人原管理员发送命令。", true); }
    catch (error) { toast(error.message, true); }
  });
  $("logout").addEventListener("click", async () => {
    try { await api("/admin/api/logout", "POST", {}); view.csrf = ""; showScreen("login-screen"); }
    catch (error) { toast(error.message, true); }
  });
  let searchTimer;
  $("product-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => {
    view.productPage = 1; loadProducts().catch((error) => toast(error.message, true));
  }, 260); });
  $("refresh-products").addEventListener("click", () => loadProducts().catch((error) => toast(error.message, true)));
  for (const [id, dir, key, loader] of [
    ["products-prev", -1, "productPage", loadProducts], ["products-next", 1, "productPage", loadProducts],
    ["movements-prev", -1, "movementPage", loadMovements], ["movements-next", 1, "movementPage", loadMovements]
  ]) $(id).addEventListener("click", () => { view[key] += dir; loader().catch((error) => toast(error.message, true)); });
  $("refresh-movements").addEventListener("click", () => { view.movementPage = 1; loadMovements().catch((error) => toast(error.message, true)); });
  $("movement-filter").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); $("refresh-movements").click(); } });
  $("stock-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const action = event.submitter?.value === "remove" ? "remove" : "add";
    const product_id = $("stock-id").value.trim();
    const quantity = Number($("stock-quantity").value);
    if (!product_id || !Number.isInteger(quantity) || quantity < 1 || quantity > 1000000000) {
      toast("请填写商品 ID 和有效正整数数量。", true); return;
    }
    for (const id of ["add-stock", "remove-stock"]) $(id).disabled = true;
    try {
      const data = await api("/admin/api/stock", "POST", { action, product_id, quantity });
      toast(data.message);
      $("stock-quantity").value = "";
      view.productPage = 1;
      view.movementPage = 1;
      await Promise.all([loadSummary(), loadProducts(), loadMovements(), loadStats()]);
    } catch (error) { toast(error.message, true); }
    finally { for (const id of ["add-stock", "remove-stock"]) $(id).disabled = false; }
  });
  $("stats-form").addEventListener("submit", (event) => { event.preventDefault(); loadStats().catch((error) => toast(error.message, true)); });
  $("stats-end").value = localDay();
  $("stats-start").value = localDay(new Date(Date.now() - 6 * 86400000));
  refreshSession().then((ready) => { if (ready) loadDashboard(); })
    .catch((error) => { showScreen("login-screen"); toast(error.message, true); });
}

document.addEventListener("DOMContentLoaded", setup);
