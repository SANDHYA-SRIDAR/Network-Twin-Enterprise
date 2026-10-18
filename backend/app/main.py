from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.network import router as network_router
from app.api.scenario import router as scenario_router
from app.api.failure_simulation import router as failure_simulation_router
from app.api.analysis import router as analysis_router
from pydantic import ValidationError
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

app = FastAPI(
    title=settings.project_name,
    openapi_url=f"{settings.api_prefix}/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Lovable/Vite may select a different localhost port; keep local dev origins working.
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(network_router, prefix=settings.api_prefix)
app.include_router(scenario_router, prefix=settings.api_prefix)
app.include_router(failure_simulation_router, prefix=settings.api_prefix)
app.include_router(analysis_router, prefix=settings.api_prefix)

@app.exception_handler(ValidationError)
@app.exception_handler(RequestValidationError)
async def invalid_model(_request, _exception):
    # Avoid reflecting user topology or configuration in runtime validation errors.
    return JSONResponse(status_code=422, content={"detail": "Invalid topology or scenario values; check finite ranges and references."})

@app.get(f"{settings.api_prefix}/health")
async def health_check():
    return {
        "status": "ok",
        "service": settings.project_name
    }


@app.get(f"{settings.api_prefix}/configuration/supabase", tags=["configuration"])
async def supabase_configuration():
    diagnostic = settings.supabase_diagnostic()
    return JSONResponse(status_code=200 if diagnostic["configuration_valid"] else 503, content=diagnostic)
