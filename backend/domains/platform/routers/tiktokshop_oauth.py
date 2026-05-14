from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/tiktokshop/callback", response_class=HTMLResponse, include_in_schema=False)
async def tiktokshop_oauth_callback(
    request: Request,
    auth_code: Optional[str] = Query(default=None, alias="auth_code"),
    code: Optional[str] = Query(default=None, alias="code"),
    state: Optional[str] = Query(default=None, alias="state"),
    error: Optional[str] = Query(default=None, alias="error"),
    error_description: Optional[str] = Query(default=None, alias="error_description"),
) -> HTMLResponse:
    """
    TikTok Shop Open API OAuth callback.

    Notes:
    - TikTok may return `auth_code` or `code` depending on the flow/config.
    - We keep this endpoint unauthenticated; it is called by the browser redirect.
    """
    resolved_code = auth_code or code

    # Keep a small in-memory breadcrumb for debugging (best-effort).
    try:
        store = getattr(request.app.state, "tiktokshop_oauth_last_callback", None)
        if store is None:
            store = {}
            request.app.state.tiktokshop_oauth_last_callback = store
        store.update(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "auth_code": resolved_code,
                "state": state,
                "error": error,
                "error_description": error_description,
                "client_ip": getattr(request.client, "host", None),
            }
        )
    except Exception:
        # Never fail the callback because of debug storage.
        pass

    if error:
        html = f"""
<!doctype html>
<html lang="zh-CN">
  <head><meta charset="utf-8"/><title>TikTok Shop 授权失败</title></head>
  <body style="font-family: -apple-system, Segoe UI, Arial; padding: 24px;">
    <h2>授权失败</h2>
    <p><b>error</b>: {error}</p>
    <p><b>description</b>: {error_description or ""}</p>
    <p>你可以关闭此页面，回到系统里重新发起授权。</p>
  </body>
</html>
"""
        return HTMLResponse(content=html, status_code=400)

    if not resolved_code:
        html = """
<!doctype html>
<html lang="zh-CN">
  <head><meta charset="utf-8"/><title>TikTok Shop 授权回调</title></head>
  <body style="font-family: -apple-system, Segoe UI, Arial; padding: 24px;">
    <h2>回调已到达，但未发现授权码</h2>
    <p>请检查回调 URL 的查询参数是否包含 <code>auth_code</code> 或 <code>code</code>。</p>
    <p>如果你看到的是空白页或平台提示错误，请把当前地址栏的完整 URL（打码后）发给我排查。</p>
  </body>
</html>
"""
        return HTMLResponse(content=html, status_code=400)

    html = f"""
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8"/>
    <title>TikTok Shop 授权成功</title>
  </head>
  <body style="font-family: -apple-system, Segoe UI, Arial; padding: 24px;">
    <h2>授权成功</h2>
    <p>已收到授权码（auth_code）。请复制下面的值，粘贴到 Postman 环境变量 <code>auth_code</code> 或你的后端配置里。</p>
    <div style="margin-top: 12px; padding: 12px; background: #f6f8fa; border: 1px solid #e5e7eb; border-radius: 8px;">
      <div style="font-size: 12px; color: #57606a; margin-bottom: 6px;">auth_code</div>
      <code style="word-break: break-all;">{resolved_code}</code>
    </div>
    <p style="margin-top: 12px; color: #57606a;">state: <code>{state or ""}</code></p>
    <p style="margin-top: 12px;">你可以关闭此页面，回到系统继续下一步（GetAccessToken）。</p>
  </body>
</html>
"""
    return HTMLResponse(content=html, status_code=200)

