"""Local HTTP adapter over the shared chat service; no public-user authentication."""

from fastapi import FastAPI, HTTPException, Request

from briefing import get_briefing_payload
from order_search import search_orders
from rules import SNAPSHOT


def create_app(service):
    app = FastAPI(title='DSS5105 Factory Assistant')

    async def body(request, allowed):
        try:
            value = await request.json()
        except ValueError:
            raise HTTPException(400, 'Body must be valid JSON.') from None
        if not isinstance(value, dict) or set(value) - set(allowed):
            raise HTTPException(400, 'Unsupported request fields.')
        return value

    def run(function, *args):
        try:
            return function(*args)
        except KeyError:
            raise HTTPException(404, 'Session not found.') from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        except Exception:
            raise HTTPException(503, 'Service unavailable. Check local database and model configuration.') from None

    @app.get('/sessions')
    def sessions():
        return run(service.list_sessions)

    @app.post('/sessions', status_code=201)
    async def create_session(request: Request):
        from starlette.concurrency import run_in_threadpool
        data = await body(request, ['title'])
        return await run_in_threadpool(run, service.create_session, data.get('title', 'New conversation'))

    @app.get('/sessions/{session_id}/messages')
    def history(session_id: str):
        return run(service.get_history, session_id)

    @app.post('/sessions/{session_id}/messages')
    async def message(session_id: str, request: Request):
        from starlette.concurrency import run_in_threadpool
        data = await body(request, ['message'])
        return await run_in_threadpool(run, service.send_message, session_id, data.get('message'))

    @app.get('/briefings/latest')
    def latest_briefing(as_of_date: str = SNAPSHOT):
        # 没有调度器之前，“最新”就是按数据快照当场生成的晨报；不调用模型。
        return run(get_briefing_payload, as_of_date)

    @app.get('/orders/search')
    def order_search(q: str = '', limit: int = 8):
        result = run(search_orders, q, limit)
        if result['status'] != 'ok':
            raise HTTPException(400, result['message'])
        return result

    return app
