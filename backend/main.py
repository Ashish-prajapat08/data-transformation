"""Local V0 API. Only CSV/Excel ingestion; no arbitrary SQL or external URL execution."""
import os
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import Response
from pydantic import Field
from models.migration import Contract, TargetSchema, ReviewDecision, crm_target
from backend.service import MigrationService
from backend.persistence import ConflictError


class Approval(Contract):
    approved: bool


class Reviews(Contract):
    decisions: list[ReviewDecision] = Field(min_length=1, max_length=500)


def create_app(service=None):
    @asynccontextmanager
    async def lifespan(app):
        load_dotenv()
        app.state.service = service or MigrationService()
        yield
        if service is None:
            app.state.service.store.engine.dispose()

    api = FastAPI(title='AI Data Migration & Transformation Agent', lifespan=lifespan)
    if service is not None:
        api.state.service = service

    @api.exception_handler(KeyError)
    async def missing(request, error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={'detail': 'Run or evaluation not found'})

    @api.exception_handler(ValueError)
    async def invalid(request, error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409 if isinstance(error, ConflictError) else 400,
                            content={'detail': str(error) if type(error) in (ValueError, ConflictError) else 'Invalid request'})

    @api.get('/health')
    def health():
        return {'status': 'ok'}

    @api.get('/targets')
    def targets():
        return [crm_target().model_dump()]

    @api.post('/migrations', status_code=201)
    async def create_migration(request: Request, file: Annotated[UploadFile, File()],
                               target_schema: Annotated[str, Form()],
                               instructions: Annotated[str, Form(max_length=4000)] = ''):
        try:
            target = TargetSchema.model_validate_json(target_schema)
        except ValueError:
            raise HTTPException(422, 'Invalid target schema') from None
        limit = int(os.getenv('MAX_UPLOAD_BYTES', '10485760'))
        content = await file.read(limit + 1)
        if len(content) > limit:
            raise HTTPException(413, 'Upload exceeds limit')
        # Parsing/model execution must not block the async event loop.
        from starlette.concurrency import run_in_threadpool
        try:
            state = await run_in_threadpool(request.app.state.service.create, content, file.filename or '', target, instructions)
        except ValueError:
            raise HTTPException(400, 'Invalid dataset; check file type, column names and limits') from None
        except Exception:
            raise HTTPException(400, 'Dataset could not be parsed') from None
        return state.model_dump(mode='json')

    @api.get('/migrations')
    def migrations(request: Request):
        return request.app.state.service.store.list_runs()

    @api.get('/migrations/{run_id}')
    def get_migration(run_id: str, request: Request):
        return request.app.state.service.store.load(run_id)[0].model_dump(mode='json')

    @api.get('/migrations/{run_id}/preview')
    def preview(run_id: str, request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        import json
        state, _ = request.app.state.service.store.load(run_id)
        frame = state.frame
        records = json.loads(frame.iloc[offset:offset + limit].to_json(orient='records'))
        return {'rows': [{'row_id': int(row_id), 'values': values} for row_id, values in
                         zip(frame.index[offset:offset + limit], records)], 'total': len(frame)}

    @api.get('/migrations/{run_id}/reviews/{item_id}/preview')
    def review_preview(run_id: str, item_id: str, request: Request):
        import json
        state, _ = request.app.state.service.store.load(run_id)
        item = next((item for item in state.review_items if item.id == item_id), None)
        if item is None:
            raise KeyError(item_id)
        frame = state.frame.loc[[row for row in item.rows[:200] if row in state.frame.index]]
        records = json.loads(frame.to_json(orient='records'))
        return [{'row_id': int(row_id), 'values': value} for row_id, value in zip(frame.index, records)]

    @api.get('/migrations/{run_id}/audit')
    def audit(run_id: str, request: Request):
        return request.app.state.service.store.load(run_id)[0].trace

    @api.post('/migrations/{run_id}/approval')
    def approval(run_id: str, body: Approval, request: Request, background_tasks: BackgroundTasks):
        state = request.app.state.service.approve(run_id, body.approved, execute=False)
        if body.approved:
            background_tasks.add_task(request.app.state.service.resume, run_id)
        return state.model_dump(mode='json')

    @api.post('/migrations/{run_id}/reviews')
    def reviews(run_id: str, body: Reviews, request: Request):
        return request.app.state.service.review(run_id, body.decisions).model_dump(mode='json')

    @api.post('/migrations/{run_id}/resume')
    def resume(run_id: str, request: Request):
        return request.app.state.service.resume(run_id).model_dump(mode='json')

    @api.get('/migrations/{run_id}/export')
    def export(run_id: str, request: Request):
        content = request.app.state.service.export(run_id)
        return Response(content, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="migration-ready.csv"'})

    @api.delete('/migrations/{run_id}', status_code=204)
    def delete_migration(run_id: str, request: Request):
        request.app.state.service.store.delete_run(run_id)
        return Response(status_code=204)

    @api.post('/evaluations')
    def evaluation(request: Request):
        from evaluation.runner import run_evaluation
        result = run_evaluation(planner=request.app.state.service.agent.planner)
        evaluation_id = str(uuid4())
        request.app.state.service.store.save_evaluation(evaluation_id, result)
        return {'evaluation_id': evaluation_id, **result}

    @api.get('/evaluations/{evaluation_id}')
    def get_evaluation(evaluation_id: str, request: Request):
        return request.app.state.service.store.load_evaluation(evaluation_id)

    return api


app = create_app()
