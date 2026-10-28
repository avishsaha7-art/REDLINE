import os
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from backend.api.routes import runs, benchmark, repositories, projects
from backend.api.cors import get_allowed_origins, ALLOWED_METHODS, ALLOWED_HEADERS
from backend.config import load_dotenv_if_present

# Load environment safely on startup without leaking secrets (REV-009)
load_dotenv_if_present()

app = FastAPI(title="REDLINE API", version="1.0")


class LocalhostOnlyMiddleware(BaseHTTPMiddleware):
    """
    Restricts API access to loopback interfaces (localhost, 127.0.0.1, ::1)
    and test clients for the local hackathon deployment model (REV-010).
    Uses the underlying socket peer IP from request.client.host, not spoofable HTTP Host headers.
    """
    LOOPBACK_IPS = {"127.0.0.1", "::1", "localhost", "testclient"}

    async def dispatch(self, request: Request, call_next):
        if os.environ.get("REDLINE_ALLOW_REMOTE_API") == "1":
            return await call_next(request)

        client_host = request.client.host if request.client else None
        if client_host and client_host not in self.LOOPBACK_IPS:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": (
                        f"Access forbidden: REDLINE API is restricted to loopback (localhost) connections only. "
                        f"Remote client '{client_host}' is rejected under the local hackathon demo threat model."
                    )
                }
            )

        return await call_next(request)


app.add_middleware(LocalhostOnlyMiddleware)

# Attach restricted CORSMiddleware for cross-origin browser integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=ALLOWED_METHODS,
    allow_headers=ALLOWED_HEADERS,
)

app.include_router(runs.router, prefix="/api/v1/runs")
app.include_router(benchmark.router, prefix="/api/v1/benchmark")
app.include_router(repositories.router, prefix="/api/v1/repositories")
app.include_router(projects.router, prefix="/api/v1/projects")


@app.get("/api/v1/health")
@app.get("/health")
def health():
    import datetime
    return {
        "status": "healthy",
        "service": "REDLINE API",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
