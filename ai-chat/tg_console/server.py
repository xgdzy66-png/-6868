from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from tg_ai.config import ConfigError, Settings
from tg_ai.engine import AIError

from .models import AccountPatch, Batch, Code, ConfigPatch, Login, NewAccount, Password, ToolRequest
from .security import COOKIE, Security
from .tools import run_tool
from .vault import public_account, public_config

STATIC = Path(__file__).parent / 'static'


def create_app(vault, manager=None, demo=False, https_cookie=False, public_origin=None):
    if manager is None:
        from .manager import Manager
        manager = Manager(vault, demo=demo)
    security = Security(vault)
    api_lock = asyncio.Lock()
    tool_slots = asyncio.Semaphore(2)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await manager.shutdown()

    app = FastAPI(title='TG Atelier', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.vault, app.state.manager, app.state.security = vault, manager, security

    @app.middleware('http')
    async def guards(request: Request, call_next):
        if request.method in ('POST', 'PATCH', 'PUT', 'DELETE'):
            origin = request.headers.get('origin')
            expected = public_origin.rstrip('/') if public_origin else str(request.base_url).rstrip('/')
            if origin and origin.rstrip('/') != expected:
                return JSONResponse({'detail': '拒绝跨站操作'}, status_code=403)
            if not request.headers.get('content-type', '').lower().startswith('application/json'):
                return JSONResponse({'detail': '请求必须使用 JSON'}, status_code=415)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 65536:
                    return JSONResponse({'detail': '请求内容过大'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self' https://manus.im https://*.manus.im"
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # 默认 Pydantic 错误会回显 input，不能把密码或 API 密钥回显。
        errors = [{'loc': e['loc'], 'msg': e['msg']} for e in exc.errors()]
        return JSONResponse({'detail': '表单内容不合法', 'errors': errors}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': '账号不存在'}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        # 本模块的 ValueError 都来自固定中文验证描述，不含用户凭据。
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.exception_handler(ConfigError)
    async def config_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.exception_handler(AIError)
    async def ai_error(request, exc):
        message = 'AI 配置或授权失败，请检查接口、模型、密钥和调用权限' if exc.fatal else 'AI 服务暂时不可用，请稍后重试'
        return JSONResponse({'detail': message}, status_code=502)

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse({'detail': '操作失败，请检查网络和后台配置；未回显敏感请求'}, status_code=500)

    def auth(request: Request):
        session = security.session(request.cookies.get(COOKIE))
        if not session:
            raise HTTPException(401, '请先登录管理员后台')
        if request.method in ('POST', 'PATCH', 'PUT', 'DELETE'):
            if not security.valid_csrf(session, request.headers.get('X-CSRF-Token')):
                raise HTTPException(403, '会话校验失败，请刷新页面重新操作')
        return session

    def dashboard():
        statuses = manager.statuses()
        accounts = [public_account(a, statuses.get(a['id'], {})) for a in vault.accounts()]
        stats = {
            'total': len(accounts), 'connected': sum(a['connected'] for a in accounts),
            'running': sum(a['state'] == 'running' for a in accounts),
            'groups': len({g for a in accounts for g in a['groups']}), 'replies_today': vault.replies_today(),
        }
        # 不将试运行草稿或发送失败尝试误报为真实已发消息数。
        return {'accounts': accounts, 'stats': stats, 'events': vault.events(),
                'config': public_config(vault.config()), 'demo': demo}

    async def action(account_id, name, *args):
        vault.account(account_id)
        from .manager import ManagerError
        try:
            async with api_lock:
                return await getattr(manager, name)(account_id, *args)
        except ManagerError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get('/healthz')
    async def health():
        return {'ok': True}

    @app.get('/api/session')
    async def session_info(request: Request):
        session = security.session(request.cookies.get(COOKIE))
        result: dict = {'authenticated': bool(session), 'demo': demo, 'configured': bool(vault.admin_hash())}
        if session:
            result['csrf'] = session.csrf
        return result

    @app.post('/api/login')
    async def login(payload: Login, request: Request):
        if not vault.admin_hash():
            raise HTTPException(503, '请先在本机终端初始化管理员')
        address = request.client.host if request.client else 'local'
        try:
            token, session = security.login(payload.password, address)
        except ValueError as exc:
            raise HTTPException(429 if '过多' in str(exc) else 401, str(exc)) from exc
        response = JSONResponse({'csrf': session.csrf})
        response.set_cookie(COOKIE, token, httponly=True, secure=https_cookie,
                            samesite='none' if https_cookie else 'strict', max_age=8 * 3600, path='/')
        return response

    @app.post('/api/logout', dependencies=[Depends(auth)])
    async def logout(request: Request):
        security.logout(request.cookies.get(COOKIE))
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE, path='/', secure=https_cookie,
                               samesite='none' if https_cookie else 'strict')
        return response

    @app.get('/api/dashboard', dependencies=[Depends(auth)])
    async def get_dashboard():
        return dashboard()

    @app.get('/api/config', dependencies=[Depends(auth)])
    async def get_config():
        return public_config(vault.config())

    @app.patch('/api/config', dependencies=[Depends(auth)])
    async def set_config(payload: ConfigPatch):
        patch = payload.model_dump(exclude_none=True)
        patch = {k: v for k, v in patch.items() if k not in ('api_hash', 'ai_key') or v}
        if demo:
            raise HTTPException(403, '演示后台不保存配置或真实密钥，请下载后在本机运行')
        async with api_lock:
            statuses = manager.statuses()
            if any(s.get('state') == 'running' for s in statuses.values()):
                raise HTTPException(409, '请先停止全部运行账号，再修改全局 AI 配置')
            if {'api_id', 'api_hash'}.intersection(patch) and any(s.get('connected') for s in statuses.values()):
                raise HTTPException(409, '请先停止并断开全部账号，再修改 Telegram 应用凭据')
            cfg = {**vault.config(), **patch}
            if cfg['api_hash'] and (len(cfg['api_hash']) != 32 or any(c not in '0123456789abcdefABCDEF' for c in cfg['api_hash'])):
                raise HTTPException(400, 'API Hash 应是 Telegram 提供的 32 位十六进制字符')
            parsed = urlparse(cfg['ai_base'])
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise HTTPException(400, 'AI 地址必须是无凭据、无查询参数的 HTTPS Base URL')
            cfg['ai_base'] = cfg['ai_base'].rstrip('/')
            if cfg['ai_base'].endswith('/chat/completions'):
                raise HTTPException(400, 'Base URL 不要包含 /chat/completions')
            Settings(ai_base=cfg['ai_base'], ai_extra_json=cfg['ai_extra_json'],
                     ai_token_parameter=cfg['ai_token_parameter']).validate()
            vault.update_config(cfg)
            vault.event(None, 'config', '已更新加密服务配置，密钥未回显')
        return public_config(cfg)

    @app.post('/api/accounts', dependencies=[Depends(auth)])
    async def add_account(payload: NewAccount):
        if demo:
            raise HTTPException(403, '演示后台不接收真实手机号，请下载后在本机添加账号')
        async with api_lock:
            record = vault.add_account(payload.name, payload.phone)
        return {'account': public_account(record, {})}

    @app.patch('/api/accounts/{account_id}', dependencies=[Depends(auth)])
    async def update_account(account_id: str, payload: AccountPatch):
        patch = payload.model_dump(exclude_none=True)
        async with api_lock:
            record = vault.account(account_id)
            if manager.statuses().get(account_id, {}).get('state') == 'running':
                raise HTTPException(409, '请先停止该账号，再修改运行配置')
            if 'features' in patch:
                patch['features'] = list(dict.fromkeys(patch['features']))
            candidate = {**record, **patch}
            # 用运行配置的完整验证捕获组合性错误。
            cfg = vault.settings(account_id)
            from dataclasses import replace
            replace(cfg, groups=frozenset(candidate['groups']), reply_mode=candidate['reply_mode'],
                    probability=candidate['probability'], cooldown=candidate['cooldown'],
                    hourly_limit=candidate['hourly_limit'], daily_limit=candidate['daily_limit']).validate()
            record = vault.update_account(account_id, patch)
            vault.event(account_id, 'config', '已更新账号功能与群聊配置')
        return {'account': public_account(record, manager.statuses().get(account_id, {}))}

    @app.post('/api/accounts/{account_id}/code/request', dependencies=[Depends(auth)])
    async def code_request(account_id: str):
        if demo:
            raise HTTPException(403, '演示环境不发送真实验证码')
        return await action(account_id, 'request_code')

    @app.post('/api/accounts/{account_id}/code/verify', dependencies=[Depends(auth)])
    async def code_verify(account_id: str, payload: Code):
        if demo:
            raise HTTPException(403, '演示环境不接收真实验证码')
        return await action(account_id, 'verify_code', payload.code)

    @app.post('/api/accounts/{account_id}/password/verify', dependencies=[Depends(auth)])
    async def password_verify(account_id: str, payload: Password):
        if demo:
            raise HTTPException(403, '演示环境不接收真实两步验证密码')
        return await action(account_id, 'verify_password', payload.password)

    @app.post('/api/accounts/{account_id}/connect', dependencies=[Depends(auth)])
    async def connect(account_id: str):
        return await action(account_id, 'connect')

    @app.post('/api/accounts/{account_id}/start', dependencies=[Depends(auth)])
    async def start(account_id: str):
        return await action(account_id, 'start')

    @app.post('/api/accounts/{account_id}/stop', dependencies=[Depends(auth)])
    async def stop(account_id: str):
        return await action(account_id, 'stop')

    @app.get('/api/accounts/{account_id}/groups', dependencies=[Depends(auth)])
    async def groups(account_id: str):
        return {'groups': await action(account_id, 'groups')}

    @app.get('/api/accounts/{account_id}/preview', dependencies=[Depends(auth)])
    async def preview(account_id: str):
        vault.account(account_id)
        return {'preview': manager.preview(account_id)}

    @app.post('/api/batch', dependencies=[Depends(auth)])
    async def batch(payload: Batch):
        async with api_lock:
            return {'results': await manager.batch(payload.action, payload.ids)}

    @app.post('/api/tools', dependencies=[Depends(auth)])
    async def tools(payload: ToolRequest):
        return await run_tool(vault, manager, payload, tool_slots, demo=demo)

    @app.get('/')
    async def index():
        return FileResponse(STATIC / 'index.html')

    @app.get('/manus-routes.json')
    async def route_manifest():
        return JSONResponse({'routes': [{'path': '/', 'title': 'TG Atelier 多账号管家后台'}]})

    app.mount('/static', StaticFiles(directory=STATIC), name='static')
    return app
