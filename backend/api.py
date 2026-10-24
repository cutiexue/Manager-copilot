"""Local HTTP adapter over the shared chat service; no public-user authentication.

Every error response has one shape, {"detail": <message for people>, "code": <stable name for
programs>}, so the frontend can always show `detail` and tests can check `code`."""

import logging
import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from briefing import get_briefing_payload
from order_search import search_orders
from rules import SNAPSHOT
from service import AgentIncompleteError, ModelUnavailableError
from storage import ConversationConflictError, SessionNotFoundError

logger = logging.getLogger('manager_copilot.api')


class ApiError(Exception):
    """An error the client should see, with its HTTP status and a stable code."""

    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _error_response(status, code, message):
    return JSONResponse({'detail': message, 'code': code}, status_code=status)


def create_app(service):
    app = FastAPI(title='DSS5105 Factory Assistant')

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return _error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def invalid_parameters(request, exc):
        # FastAPI's own 422 body is a list; turn the first problem into one readable sentence.
        problem = exc.errors()[0] if exc.errors() else {}
        where = '.'.join(str(part) for part in problem.get('loc', ())[1:]) or 'request'
        return _error_response(400, 'INVALID_REQUEST', f"{where}: {problem.get('msg', 'invalid value')}.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        code = {404: 'NOT_FOUND', 405: 'METHOD_NOT_ALLOWED'}.get(exc.status_code, 'HTTP_ERROR')
        return _error_response(exc.status_code, code, str(exc.detail))

    async def body(request, allowed):
        try:
            value = await request.json()
        except ValueError:
            raise ApiError(400, 'INVALID_REQUEST', 'Body must be valid JSON.') from None
        if not isinstance(value, dict) or set(value) - set(allowed):
            raise ApiError(400, 'INVALID_REQUEST', 'Unsupported request fields.')
        return value

    def run(function, *args):
        """Call the service and turn each kind of failure into the response that describes it."""
        try:
            return function(*args)
        except SessionNotFoundError:
            raise ApiError(404, 'SESSION_NOT_FOUND', 'Session not found.') from None
        except ConversationConflictError as exc:
            raise ApiError(409, 'CONFLICT', str(exc)) from None
        except ValueError as exc:
            raise ApiError(400, 'INVALID_REQUEST', str(exc)) from None
        except AgentIncompleteError as exc:
            logger.warning('Agent did not finish: %s', exc)
            raise ApiError(502, 'AGENT_INCOMPLETE', f'{exc} Try asking a narrower question.') from None
        except ModelUnavailableError as exc:
            logger.warning('Model API unavailable: %r', exc.__cause__)
            raise ApiError(503, 'MODEL_UNAVAILABLE', str(exc)) from None
        except sqlite3.Error:
            logger.exception('Local database error')
            raise ApiError(503, 'DATABASE_ERROR', 'The local database could not be used; see the backend log.') from None
        except Exception:
            # Anything else is a bug (including a stray KeyError): keep the traceback for the log.
            logger.exception('Unexpected error in %s', getattr(function, '__name__', function))
            raise ApiError(500, 'INTERNAL_ERROR', 'Internal error in the backend; see the backend log.') from None

    @app.get('/sessions')
    def sessions():
        return run(service.list_sessions)

    @app.post('/sessions', status_code=201)
    async def create_session(request: Request):
        data = await body(request, ['title'])
        return await run_in_threadpool(run, service.create_session, data.get('title', 'New conversation'))

    @app.get('/sessions/{session_id}/messages')
    def history(session_id: str):
        return run(service.get_history, session_id)

    @app.post('/sessions/{session_id}/messages')
    async def message(session_id: str, request: Request):
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
            raise ApiError(400, 'INVALID_REQUEST', result['message'])
        return result

    return app
