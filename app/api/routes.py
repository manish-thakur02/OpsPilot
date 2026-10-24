from pathlib import Path
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
from app.api.schemas import ChatRequest, ChatResponse, MetricResponse
from app.services.analytics import Analytics, Filters, ToolRequest
from app.agents.graph import build_graph
from app.config import settings
from app.database.connection import readonly

router = APIRouter()
analytics_service = Analytics()
copilot_graph = build_graph()

def get_analytics():
    return analytics_service

def get_graph():
    return copilot_graph

@router.get('/health')
def health():
    with readonly(analytics_service.db) as conn:
        count = conn.execute('SELECT COUNT(*) FROM incident_summary').fetchone()[0]
    policy_ready = (settings.chroma / 'manifest.json').is_file()
    return {'status': 'ok' if policy_ready else 'policy_index_missing', 'mode': settings.mode, 'database_ready': True, 'policy_index_ready': policy_ready, 'incident_count': count}

@router.get('/data/summary', response_model=MetricResponse)
def summary(filters: Annotated[Filters, Query()], service: Annotated[Analytics, Depends(get_analytics)]):
    return service.run(ToolRequest(tool='overview', filters=filters))

@router.get('/analytics/priorities', response_model=MetricResponse)
def priorities(filters: Annotated[Filters, Query()], service: Annotated[Analytics, Depends(get_analytics)]):
    return service.run(ToolRequest(tool='priorities', filters=filters))

@router.get('/analytics/states', response_model=MetricResponse)
def states(filters: Annotated[Filters, Query()], service: Annotated[Analytics, Depends(get_analytics)]):
    return service.run(ToolRequest(tool='states', filters=filters))

@router.get('/analytics/trends', response_model=MetricResponse)
def trends(filters: Annotated[Filters, Query()], service: Annotated[Analytics, Depends(get_analytics)]):
    return service.run(ToolRequest(tool='trends', filters=filters))

@router.post('/analytics/query', response_model=MetricResponse)
def approved_query(request: ToolRequest, service: Annotated[Analytics, Depends(get_analytics)]):
    return service.run(request)

@router.get('/incidents/{incident_id}', response_model=MetricResponse)
def incident(incident_id: Annotated[str, PathParam(pattern=r'^INC\d{7}$')], service: Annotated[Analytics, Depends(get_analytics)]):
    return service.run(ToolRequest(tool='incident', incident_id=incident_id))

@router.post('/chat', response_model=ChatResponse)
def chat(request: ChatRequest, graph=Depends(get_graph)):
    state = graph.invoke({'question': request.question}, config={'recursion_limit': 12})
    response = ChatResponse(answer=state['answer'], route=state['intent'], sources=state['sources'], analytics=state['analytics'], errors=state['errors'], execution={'mode': state['mode'], 'tools': state['selected_tools'], 'parameters': state.get('tool_request', {}), 'trace': state['trace'], 'elapsed_ms': state['elapsed_ms'], 'status': 'partial' if state['errors'] and state['sources'] else 'error' if state['errors'] else 'ok'})
    if state['errors'] and not state['sources']:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=response.model_dump())
    return response
