from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.mininet import router as mininet_router

app = FastAPI(
    title=settings.project_name,
    openapi_url=f"{settings.api_prefix}/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(mininet_router, prefix=settings.api_prefix)

@app.get(f"{settings.api_prefix}/health")
async def health_check():
    return {
        "status": "ok",
        "service": settings.project_name
    }
