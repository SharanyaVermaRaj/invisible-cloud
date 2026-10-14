"""The web server: the API under /api, and the built web app for everything else.

Run locally:  uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import settings
from app.db import Base, engine

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
app.include_router(router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


if (STATIC / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")


def _index():
    index = STATIC / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>Frontend not built</h1><p>Run <code>cd frontend && npm install && "
                            "npm run build</code>. The API is at <a href='/api/docs'>/api/docs</a>.</p>")
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    candidate = (STATIC / path).resolve()
    if path and candidate.is_file() and STATIC.resolve() in candidate.parents:
        return FileResponse(candidate)
    if path in ("", "app") or path.startswith("app/"):
        return _index()
    raise HTTPException(404, "Not found")
