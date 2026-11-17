from threading import Lock
from typing import Annotated
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field, ConfigDict
from app.core.config import get_settings
from app.kubernetes.contexts import list_contexts, resolve_context
from app.kubernetes.executor import KubectlExecutor
from app.services.summary import summarize
from loguru import logger
from app.ai.agent import analyze_investigation
from app.api.auth import require_user
from app.services.insforge import InsForge, get_insforge
from app.services.history import InvestigationHistory
from app.services.investigation import investigate_cluster

router = APIRouter()
_lock = Lock()

class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    context: str = Field(min_length=1, max_length=1024)

@router.get('/clusters')
def clusters(user: Annotated[dict, Depends(require_user)], response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return {'clusters': list_contexts()}

@router.post('/investigate')
def investigate(user: Annotated[dict, Depends(require_user)],
                service: Annotated[InsForge, Depends(get_insforge)],
                response: Response,
                x_investigation_id: Annotated[UUID | None, Header()] = None,
                body: InvestigationRequest | None = None):
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, 'An investigation is already running')
    history = None
    started = False
    try:
        cluster = resolve_context(body.context if body else None)
        history = InvestigationHistory(user['id'], x_investigation_id or uuid4(), service, cluster=cluster)
        # Do not begin cluster access when history setup is unavailable.
        history.start()
        started = True
        result = investigate_cluster(executor=KubectlExecutor(get_settings(), context=cluster['context']), progress=history.update)
        result['cluster'] = cluster
        result['summary'] = summarize(result)
        history.update('ai', 'running')
        ai = analyze_investigation(result)
        history.update('ai', 'completed' if ai.get('status') == 'success' else 'error')
        result['ai'] = {k: v for k, v in ai.items() if k != 'diagnosis'}
        result['diagnosis'] = ai.get('diagnosis')
        run_status = history.finish(result)
        result['investigation_id'] = history.run_id
        result['run_status'] = run_status
        result['history_saved'] = not history.warning
        response.headers['Cache-Control'] = 'no-store'
        return result
    except HTTPException:
        if started and history:
            history.finish(failed=True)
        raise
    except Exception as exc:
        if started and history:
            history.finish(failed=True)
        logger.error('Investigation stopped unexpectedly ({})', type(exc).__name__)
        raise HTTPException(500, 'The investigation stopped unexpectedly. Review saved history before retrying; check backend logs.') from None
    finally:
        _lock.release()

@router.get('/investigations')
def list_investigations(user: Annotated[dict, Depends(require_user)],
                        service: Annotated[InsForge, Depends(get_insforge)], response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return {'investigations': service.records('GET', user['id'], limit=20)}

@router.get('/investigations/{run_id}')
def get_investigation(run_id: UUID, user: Annotated[dict, Depends(require_user)],
                      service: Annotated[InsForge, Depends(get_insforge)], response: Response):
    rows = service.records('GET', user['id'], run_id=str(run_id), limit=1)
    if not rows:
        raise HTTPException(404, 'Investigation not found')
    response.headers['Cache-Control'] = 'no-store'
    return rows[0]
