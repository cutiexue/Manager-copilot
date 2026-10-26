"""Local HTTP adapter over the shared chat service; no public-user authentication.

Every error response has one shape, {"detail": <message for people>, "code": <stable name for
programs>}, so the frontend can always show `detail` and tests can check `code`. A NOT_FOUND for an
order also lists `candidates`, the closest order IDs.

Read-only views (an order, a stage's output, feasibility estimates, one cited CSV row) run the
agent's own tools, so they give the same numbers as the chat.

Follow-ups: the agent can only create proposals; POST /actions/{id}/confirm, called when the
manager presses Confirm, is the only way one is carried out. /dev/* routes are demo controls for
the scripted watch snapshots and manual briefing runs.
"""

import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

import views
import watches
from actions import ActionNotFoundError, ActionStateError, now_sg
from briefing import get_briefing_payload
from order_search import search_orders
from rules import SNAPSHOT
from scheduler import run_morning_briefing
from service import AgentIncompleteError, ModelUnavailableError
from storage import ConversationConflictError, SessionNotFoundError

logger = logging.getLogger('manager_copilot.api')


class ApiError(Exception):
    """An error the client should see, with its HTTP status and a stable code."""

    def __init__(self, status, code, message, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def _error_response(status, code, message, extra=None):
    return JSONResponse({'detail': message, 'code': code, **(extra or {})}, status_code=status)


def create_app(service, scheduler=None):
    @asynccontextmanager
    async def lifespan(app):
        if scheduler is not None:
            scheduler.start()
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown()

    app = FastAPI(title='DSS5105 Factory Assistant', lifespan=lifespan)
    actions = service.actions

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return _error_response(exc.status, exc.code, exc.message, exc.extra)

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
        except views.NotFoundError as exc:
            extra = {'candidates': exc.candidates} if exc.candidates else {}
            raise ApiError(404, 'NOT_FOUND', str(exc), **extra) from None
        except ActionNotFoundError as exc:
            raise ApiError(404, 'NOT_FOUND', str(exc)) from None
        except ConversationConflictError as exc:
            raise ApiError(409, 'CONFLICT', str(exc)) from None
        except ActionStateError as exc:
            raise ApiError(409, 'ACTION_STATE', str(exc)) from None
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

    # ---- conversations ---------------------------------------------------------------------------
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

    # ---- briefing and orders ------------------------------------------------------------------------
    @app.get('/briefings/latest')
    def latest_briefing(as_of_date: str = SNAPSHOT):
        # Generated on request from the deterministic tools (no model call), so it never goes stale;
        # the scheduler keeps a dated copy each morning (GET /briefings).
        return run(get_briefing_payload, as_of_date)

    @app.get('/briefings')
    def briefing_runs(limit: int = 30):
        return run(actions.list_briefing_runs, max(1, min(limit, 100)))

    @app.get('/orders/search')
    def order_search(q: str = '', limit: int = 8):
        result = run(search_orders, q, limit)
        if result['status'] != 'ok':
            raise ApiError(400, 'INVALID_REQUEST', result['message'])
        return result

    @app.get('/orders/{order_id}')
    def order_detail(order_id: str):
        return run(views.order_detail, order_id, actions)

    @app.get('/production/stages/{stage}')
    def stage_output(stage: str, date: str | None = None, baseline_days: int = 7, days: int = 10):
        return run(views.stage_output, stage, date, baseline_days, days)

    @app.get('/feasibility/estimators')
    def feasibility_estimators():
        return run(views.estimators)

    @app.post('/feasibility/estimate')
    async def feasibility_estimate(request: Request):
        data = await body(request, ['estimator', 'arguments'])
        return await run_in_threadpool(run, views.estimate, data.get('estimator'), data.get('arguments', {}))

    @app.get('/evidence/{evidence_id}')
    def evidence(evidence_id: str):
        return run(views.evidence_row, evidence_id)

    # ---- follow-ups: proposals and what confirming them creates --------------------------------------
    @app.get('/actions')
    def list_actions(status: str | None = None, session_id: str | None = None):
        return run(actions.list_proposals, status, session_id)

    @app.post('/actions/proposals', status_code=201)
    async def create_proposal(request: Request):
        data = await body(request, ['kind', 'payload', 'reason', 'session_id'])
        return await run_in_threadpool(run, lambda: actions.propose(
            data.get('kind'), data.get('payload'), 'ui', data.get('session_id'), data.get('reason')))

    @app.post('/actions/{proposal_id}/confirm')
    def confirm_action(proposal_id: str):
        return run(actions.confirm, proposal_id)

    @app.post('/actions/{proposal_id}/cancel')
    def cancel_action(proposal_id: str):
        return run(actions.cancel, proposal_id)

    @app.get('/follow-ups/counts')
    def follow_up_counts():
        return run(actions.counts)

    @app.get('/reminders')
    def reminders(status: str | None = None):
        return run(actions.list_reminders, status)

    @app.post('/reminders/{reminder_id}/dismiss')
    def dismiss_reminder(reminder_id: str):
        return run(actions.dismiss_reminder, reminder_id)

    @app.get('/notes')
    def notes(order_id: str | None = None):
        return run(actions.list_notes, order_id)

    @app.get('/drafts')
    def drafts():
        return run(actions.list_drafts)

    @app.get('/watches')
    def list_watches(status: str | None = None):
        return run(actions.list_watches, status)

    @app.get('/watches/{watch_id}')
    def watch_detail(watch_id: str):
        return run(lambda: {**actions.get_watch(watch_id), 'checks': actions.watch_checks(watch_id)})

    @app.post('/watches/{watch_id}/{change}')
    def change_watch(watch_id: str, change: str):
        if change not in ('pause', 'resume', 'cancel'):
            raise ApiError(404, 'NOT_FOUND', 'Use pause, resume or cancel.')
        return run(actions.set_watch_status, watch_id, change)

    @app.get('/alerts')
    def alerts(unread: bool = False):
        return run(actions.list_alerts, unread)

    @app.post('/alerts/{alert_id}/read')
    def read_alert(alert_id: str):
        return run(actions.mark_alert_read, alert_id)

    @app.get('/audit')
    def audit(limit: int = 100):
        return run(actions.list_audit, max(1, min(limit, 500)))

    # ---- data snapshots for watches, scheduler status and demo controls -------------------------------
    def snapshot_state():
        current = actions.data_version()
        upcoming = watches.next_version(current)
        return {'current': watches.version_info(current),
                'next': watches.version_info(upcoming) if upcoming else None,
                'versions': [watches.version_info(v['version']) for v in watches.load_snapshots()]}

    @app.get('/data/snapshot')
    def data_snapshot():
        return run(snapshot_state)

    @app.post('/dev/data/advance')
    def advance_snapshot():
        def advance():
            upcoming = watches.next_version(actions.data_version())
            if upcoming is None:
                raise ActionStateError('This is the last scripted snapshot.')
            actions.set_data_version(upcoming)
            check = watches.check_watches(actions, now_sg())
            return {**snapshot_state(), 'check': check}
        return run(advance)

    @app.post('/dev/data/reset')
    def reset_snapshot():
        return run(lambda: (actions.set_data_version(watches.BASE_VERSION), snapshot_state())[1])

    @app.post('/dev/briefings/generate', status_code=201)
    def generate_briefing():
        return run(lambda: run_morning_briefing(actions, now_sg(), trigger='manual'))

    @app.get('/scheduler')
    def scheduler_status():
        return scheduler.status() if scheduler is not None else {'running': False, 'jobs': []}

    return app
