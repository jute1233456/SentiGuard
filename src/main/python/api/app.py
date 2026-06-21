"""FastAPI 应用入口。

启动方式（在仓库根目录执行）：

    uvicorn src.main.python.api.app:app --host 0.0.0.0 --port 8000 --reload

环境变量：
    INTERNAL_API_TOKEN  服务间共享密钥；未设置时使用默认 dev-internal-token
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.main.python.api.routers import fact_check, hotspots

app = FastAPI(
    title="SentiGuard Internal API",
    description="Spring Boot 后端 ↔ Python FastAPI 智能体服务之间的内部接口",
    version="0.4.0",
)

app.include_router(hotspots.router)
app.include_router(fact_check.router)


# ---------------------------------------------------------------------------
# 全局异常处理：保证错误响应也符合统一响应体格式
# ---------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        body = {"code": detail["code"], "message": detail.get("message", ""), "data": None}
    else:
        body = {"code": exc.status_code * 100 + 1, "message": str(detail), "data": None}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"code": 40001, "message": exc.errors()[0].get("msg", "invalid params"), "data": None},
    )


@app.get("/internal/v1/health", tags=["health"], summary="健康检查")
def health() -> dict:
    return {"code": 0, "message": "ok", "data": {"status": "ok", "version": app.version}}
