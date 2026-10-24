from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.api.routes import router
from app.database.connection import DatabaseUnavailable

app = FastAPI(title='OpsPilot — Agentic Knowledge & Analytics Copilot', version='1.0.0', description='Real UCI incident analytics and separately labelled synthetic policy evidence. Local demonstration application.')
app.include_router(router)

@app.exception_handler(DatabaseUnavailable)
async def database_error(request: Request, exc: DatabaseUnavailable):
    return JSONResponse(status_code=503, content={'detail': str(exc)})

@app.exception_handler(LookupError)
async def not_found(request: Request, exc: LookupError):
    return JSONResponse(status_code=404, content={'detail': str(exc)})
