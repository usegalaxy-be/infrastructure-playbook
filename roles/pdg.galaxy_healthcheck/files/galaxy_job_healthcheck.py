#!/usr/bin/env python3
"""Submit test jobs to Galaxy via BioBlend and report per-tool health to InfluxDB.

health probe: run from cron, it exercises real end-to-end job execution
(container resolution, staging, compute, output) for a small set of test tools and
records whether each finished 'ok'.

Config comes from environment variables (see load_config); secrets are never logged.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from bioblend.galaxy import GalaxyInstance

log = logging.getLogger("galaxy_job_healthcheck")


@dataclass
class Config:
    galaxy_url: str
    api_key: str
    tools: list[dict]
    job_timeout: int = 600
    poll_interval: int = 15
    # Total attempts per tool (initial + retries). A tool is only reported failed
    # once it has failed this many times in a row, so transient blips don't page.
    retries: int = 3
    retry_delay: int = 30
    keep_history: bool = False
    influx_url: str | None = None
    influx_db: str = "galaxy"
    influx_user: str | None = None
    influx_pass: str | None = None
    influx_measurement: str = "galaxy_job_healthcheck"
    influx_error_measurement: str = "galaxy_job_healthcheck_error"
    host_tag: str = ""


def load_config() -> Config:
    """Build config from env. GALAXY_URL and GALAXY_API_KEY are required.

    HEALTHCHECK_TOOLS is JSON: [{"tool_id": "...", "inputs": {...}}, ...].
    """
    url = os.environ.get("GALAXY_URL", "").rstrip("/")
    api_key = os.environ.get("GALAXY_API_KEY", "")
    if not url or not api_key:
        sys.exit("GALAXY_URL and GALAXY_API_KEY are required")
    # Tool list comes from a JSON file (avoids shell-quoting JSON in a sourced env file);
    # HEALTHCHECK_TOOLS inline JSON is still honoured as a fallback.
    tools_file = os.environ.get("HEALTHCHECK_TOOLS_FILE", "")
    if tools_file:
        try:
            with open(tools_file) as fh:
                tools_raw = fh.read()
        except OSError as exc:
            sys.exit(f"cannot read HEALTHCHECK_TOOLS_FILE {tools_file}: {exc}")
    else:
        tools_raw = os.environ.get("HEALTHCHECK_TOOLS", "[]")
    try:
        tools = json.loads(tools_raw)
    except json.JSONDecodeError as exc:
        sys.exit(f"tool list is not valid JSON: {exc}")
    host_tag = os.environ.get("HEALTHCHECK_HOST_TAG") or urllib.parse.urlparse(url).hostname or ""
    return Config(
        galaxy_url=url,
        api_key=api_key,
        tools=tools,
        job_timeout=int(os.environ.get("HEALTHCHECK_JOB_TIMEOUT", "600")),
        poll_interval=int(os.environ.get("HEALTHCHECK_POLL_INTERVAL", "15")),
        retries=max(1, int(os.environ.get("HEALTHCHECK_RETRIES", "3"))),
        retry_delay=int(os.environ.get("HEALTHCHECK_RETRY_DELAY", "30")),
        keep_history=os.environ.get("HEALTHCHECK_KEEP_HISTORY", "").lower() in ("1", "true", "yes"),
        influx_url=(os.environ.get("HEALTHCHECK_INFLUX_URL") or None),
        influx_db=os.environ.get("HEALTHCHECK_INFLUX_DB", "galaxy"),
        influx_user=(os.environ.get("HEALTHCHECK_INFLUX_USER") or None),
        influx_pass=(os.environ.get("HEALTHCHECK_INFLUX_PASS") or None),
        influx_measurement=os.environ.get("HEALTHCHECK_INFLUX_MEASUREMENT", "galaxy_job_healthcheck"),
        influx_error_measurement=os.environ.get(
            "HEALTHCHECK_INFLUX_ERROR_MEASUREMENT", "galaxy_job_healthcheck_error"
        ),
        host_tag=host_tag,
    )


@dataclass
class Result:
    tool_id: str
    state: str = "unsubmitted"  # unsubmitted | ok | error | timeout
    stderr: str = ""
    job_id: str = ""
    attempts: int = 0  # how many times this tool was run; >1 with state==ok means a recovered transient


@dataclass
class Run:
    results: list[Result] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.state == "ok" for r in self.results)

    def summary(self) -> str:
        # Annotate recovered-after-retry tools so transients are visible in the log.
        return ", ".join(
            f"{r.tool_id}={r.state}" + (f"(x{r.attempts})" if r.attempts > 1 else "") for r in self.results
        )


def _line_escape(value: str) -> str:
    """Escape a tag value for InfluxDB line protocol."""
    return value.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def write_metrics(cfg: Config, run: Run) -> None:
    """Write one point per tool to InfluxDB (line protocol).

    <measurement>,host=<h>,tool=<t> ok=<0|1>i,attempts=<n>i
    <error_measurement>,host=<h>,tool=<t>,outcome=<transient|persistent> error="<stderr>"

    ok reflects the final state after retries: a tool that failed then recovered is
    ok=1 with attempts>1. The error line is written whenever a tool failed at least
    once; outcome=transient means it recovered on retry, persistent means it never did.
    So the main alert (min(ok)) only pages on persistent failures, while attempts>1 /
    outcome=transient keep intermittent flakiness visible without paging.
    """
    if not cfg.influx_url:
        return
    lines: list[str] = []
    host = _line_escape(cfg.host_tag)
    for r in run.results:
        tool = _line_escape(r.tool_id)
        ok = 1 if r.state == "ok" else 0
        lines.append(f"{cfg.influx_measurement},host={host},tool={tool} ok={ok}i,attempts={r.attempts}i")
        # Record error detail for any tool that failed at least once, tagged by whether
        # it ultimately recovered (transient) or not (persistent).
        if r.state != "ok" or r.attempts > 1:
            outcome = "persistent" if r.state != "ok" else "transient"
            # field string values: escape backslash and double-quote, collapse newlines
            err = r.stderr.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")[:500]
            lines.append(
                f'{cfg.influx_error_measurement},host={host},tool={tool},outcome={outcome} error="{err}"'
            )
    body = "\n".join(lines).encode()
    params = urllib.parse.urlencode({"db": cfg.influx_db, "precision": "s"})
    req = urllib.request.Request(f"{cfg.influx_url}/write?{params}", data=body, method="POST")
    if cfg.influx_user is not None:
        import base64

        token = base64.b64encode(f"{cfg.influx_user}:{cfg.influx_pass}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    try:
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.URLError as exc:
        log.warning("InfluxDB write failed: %s", exc)


def _submit_and_poll(gi: GalaxyInstance, cfg: Config, specs: list[dict], hist_id: str, by_id: dict[str, Result]) -> None:
    """Submit one attempt for each spec into hist_id, poll to terminal/timeout, update results.

    Resets state/job_id for the tools being (re)run but keeps stderr from a prior failed
    attempt, so a tool that recovers still carries its last failure detail for reporting.
    A spec with type "fetch" exercises the data upload/fetch path via pasted content;
    anything else runs a tool by id.
    """
    job_to_tool: dict[str, str] = {}
    for spec in specs:
        tid = spec["tool_id"]
        res = by_id[tid]
        res.state = "unsubmitted"
        res.job_id = ""
        res.attempts += 1
        try:
            if spec.get("type") == "fetch":
                resp = gi.tools.paste_content(spec.get("content", "healthcheck"), hist_id)
            else:
                resp = gi.tools.run_tool(history_id=hist_id, tool_id=tid, tool_inputs=spec.get("inputs", {}))
            jobs = resp.get("jobs", [])
            if not jobs:
                res.state = "error"
                res.stderr = "no job created on submission"
                continue
            jid = jobs[0]["id"]
            res.job_id = jid
            job_to_tool[jid] = tid
        except Exception as exc:  # bioblend raises on HTTP errors / bad inputs
            res.state = "error"
            res.stderr = f"submission failed: {exc}"[:500]

    deadline = time.time() + cfg.job_timeout
    pending = set(job_to_tool)
    while pending and time.time() < deadline:
        time.sleep(cfg.poll_interval)
        for jid in list(pending):
            try:
                state = gi.jobs.show_job(jid).get("state", "")
            except Exception as exc:
                log.warning("could not poll job %s: %s", jid, exc)
                continue
            if state in ("ok", "error", "deleted"):
                pending.discard(jid)
                res = by_id[job_to_tool[jid]]
                res.state = "ok" if state == "ok" else "error"
                if state != "ok":
                    res.stderr = _fetch_stderr(gi, jid)
    for jid in pending:  # never reached terminal state
        by_id[job_to_tool[jid]].state = "timeout"


def run_healthcheck(cfg: Config) -> Run:
    gi = GalaxyInstance(url=cfg.galaxy_url, key=cfg.api_key)
    run = Run(results=[Result(tool_id=t["tool_id"]) for t in cfg.tools])
    by_id = {r.tool_id: r for r in run.results}
    spec_by_id = {t["tool_id"]: t for t in cfg.tools}

    hist = gi.histories.create_history(name=f"job-healthcheck {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    hist_id = hist["id"]
    log.info("created history %s", hist_id)

    # Run all tools, then re-run only the ones still failing, up to cfg.retries attempts.
    # A tool is reported failed only after failing every attempt in a row, so a transient
    # blip (an iRODS reset, a momentary cluster hiccup) does not page.
    pending_specs = list(cfg.tools)
    for attempt in range(1, cfg.retries + 1):
        if attempt > 1:
            log.warning(
                "retry %d/%d for: %s", attempt, cfg.retries, ", ".join(s["tool_id"] for s in pending_specs)
            )
            time.sleep(cfg.retry_delay)
        _submit_and_poll(gi, cfg, pending_specs, hist_id, by_id)
        pending_specs = [spec_by_id[r.tool_id] for r in run.results if r.state != "ok"]
        if not pending_specs:
            break

    if cfg.keep_history:
        log.info("keeping history %s for inspection", hist_id)
    else:
        try:
            gi.histories.delete_history(hist_id, purge=True)
        except Exception as exc:
            log.warning("could not purge history %s: %s", hist_id, exc)
    return run


def _fetch_stderr(gi: GalaxyInstance, job_id: str) -> str:
    try:
        job = gi.jobs.show_job(job_id, full_details=True)
        return (job.get("tool_stderr") or job.get("stderr") or "")[:500]
    except Exception:
        return ""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if not cfg.tools:
        log.info("no tools configured; nothing to do")
        return 0
    try:
        run = run_healthcheck(cfg)
    except Exception as exc:
        # Probe-level failure (e.g. Galaxy unreachable): log, but stay non-gating.
        log.error("healthcheck aborted: %s", exc)
        return 0
    write_metrics(cfg, run)
    level = logging.INFO if run.ok else logging.WARNING
    log.log(level, "healthcheck %s: %s", "OK" if run.ok else "DEGRADED", run.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
