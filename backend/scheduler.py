"""Background jobs (APScheduler): the 07:00 morning briefing, reminder alerts, watch checks and
proposal expiry.

SQLite is the source of truth and the jobs only scan it, so a restart loses nothing and repeating
a job does nothing new: the scheduled briefing has one run key per day and every alert has a
dedupe key. Each job body is a plain function of `now`, so tests drive them with a fake clock
instead of waiting. Times are Asia/Singapore (the application clock); the briefing's content
still uses the dataset date.
"""

import logging
import re

from apscheduler.schedulers.background import BackgroundScheduler

import watches
from actions import APP_TZ, now_sg
from briefing import get_briefing_payload
from rules import SNAPSHOT

logger = logging.getLogger("manager_copilot.scheduler")


def run_morning_briefing(actions, now, trigger="scheduler"):
    """Generate and store the briefing; a scheduled run happens at most once per day."""
    run_key = f"briefing:{now.date().isoformat()}" if trigger == "scheduler" else f"manual:{now.isoformat()}"
    payload = get_briefing_payload(SNAPSHOT)
    payload["generator"] = "scheduled 07:00 run" if trigger == "scheduler" else "manual run"
    run, created = actions.save_briefing_run(run_key, payload, trigger, now)
    if created and trigger == "scheduler":
        actions.raise_alert("briefing", run["id"], "Morning briefing ready",
                            f"Data as of {payload['briefing']['as_of_date']}", run_key, now)
    return {"run": run, "created": created}


def run_reminders(actions, now):
    return {"fired": actions.fire_due_reminders(now)}


def run_watch_check(actions, now):
    return watches.check_watches(actions, now)


def run_expiry(actions, now):
    return {"expired": actions.expire_stale(now)}


JOBS = {"morning_briefing": run_morning_briefing, "reminders": run_reminders,
        "watch_check": run_watch_check, "proposal_expiry": run_expiry}


def _clock_time(value):
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value or "")
    if not match or not (0 <= int(match.group(1)) <= 23 and 0 <= int(match.group(2)) <= 59):
        raise ValueError("BRIEFING_TIME must look like 07:00.")
    return int(match.group(1)), int(match.group(2))


class AppScheduler:
    def __init__(self, actions, briefing_time="07:00", watch_minutes=1, clock=now_sg):
        if type(watch_minutes) is not int or not 1 <= watch_minutes <= 1440:
            raise ValueError("WATCH_CHECK_MINUTES must be an integer from 1 to 1440.")
        self.actions, self.clock = actions, clock
        self.briefing_at = _clock_time(briefing_time)
        self.last = {}
        self.scheduler = BackgroundScheduler(timezone=APP_TZ, job_defaults={
            "coalesce": True, "max_instances": 1, "misfire_grace_time": 3600})
        hour, minute = self.briefing_at
        self.scheduler.add_job(self.run, "cron", hour=hour, minute=minute, args=["morning_briefing"],
                               id="morning_briefing")
        self.scheduler.add_job(self.run, "interval", minutes=1, args=["reminders"], id="reminders")
        self.scheduler.add_job(self.run, "interval", minutes=watch_minutes, args=["watch_check"], id="watch_check")
        self.scheduler.add_job(self.run, "interval", minutes=10, args=["proposal_expiry"], id="proposal_expiry")

    def run(self, name):
        """Run one job now; a failure is logged and audited instead of stopping the scheduler."""
        now = self.clock()
        try:
            detail = JOBS[name](self.actions, now)
            self.last[name] = {"at": now.isoformat(), "ok": True}
            return detail
        except Exception as exc:
            logger.exception("Scheduled job %s failed", name)
            self.last[name] = {"at": now.isoformat(), "ok": False, "error": str(exc)}
            try:
                self.actions.record("scheduler", "job_failed", {"job": name, "error": str(exc)}, now)
            except Exception:
                logger.exception("Could not audit the failure of %s", name)
            return None

    def start(self):
        self.scheduler.start()
        # Catch up once at start: anything that came due while the app was closed happens now.
        for name in ("reminders", "watch_check", "proposal_expiry"):
            self.run(name)
        now = self.clock()
        if (now.hour, now.minute) >= self.briefing_at:
            self.run("morning_briefing")  # today's run key makes this a no-op if it already ran

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def status(self):
        return {"running": self.scheduler.running, "timezone": "Asia/Singapore",
                "briefing_time": "%02d:%02d" % self.briefing_at,
                "jobs": [{"id": job.id, "next_run": getattr(job, "next_run_time", None) and job.next_run_time.isoformat(),
                          "last": self.last.get(job.id)} for job in self.scheduler.get_jobs()]}
