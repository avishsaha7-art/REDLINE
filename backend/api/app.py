from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import runs, benchmark
from backend.api.cors import get_allowed_origins, ALLOWED_METHODS, ALLOWED_HEADERS

app = FastAPI(title="REDLINE API", version="1.0")

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
