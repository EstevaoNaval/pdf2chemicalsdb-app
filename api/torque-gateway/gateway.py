#!/usr/bin/env python3
"""HTTP gateway in front of the Torque 6.1.3 client commands.

Sits in the CentOS 7 gateway container, after docker-entrypoint.sh has started
trqauthd and dropped to the service user. The Celery worker calls this process.
It does not parse qstat itself.

Input: JSON over HTTP on the project network, plus qsub/qstat/qdel on PATH.
Output: JSON job id, status, or delete result.

Standard library only. Python 3.6, the python3 package shipped by CentOS 7.
Private container network only: this is not hardened for public exposure.

Endpoints (JSON; everything except /health needs "Authorization: Bearer <token>"):
  GET    /health          liveness + Torque reachability (qstat -q)
  POST   /jobs            {"script": "..."}  -> 201 {"job_id": "..."}
                         PBS directives live in the script. qsub gets no extra flags.
  GET    /jobs/<job_id>   job status (parsed from `qstat -f`)
  DELETE /jobs/<job_id>   cancel a job (qdel)
"""
import hmac
import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import unquote

HOST = os.environ.get("GATEWAY_HOST", "0.0.0.0")
PORT = int(os.environ.get("GATEWAY_PORT", "8080"))
CMD_TIMEOUT = int(os.environ.get("GATEWAY_CMD_TIMEOUT", "60"))
MAX_BODY = int(os.environ.get("GATEWAY_MAX_BODY", str(1024 * 1024)))

# Job ids are passed as a separate argv item (no shell) and checked anyway.
JOB_ID_RE = re.compile(r"^[0-9]+(\[[0-9]*\])?(\.[A-Za-z0-9_.-]+)?$")
JOB_PATH_RE = re.compile(r"^/jobs/([^/?#]+)$")
# Top-level attribute lines of `qstat -f` are indented with 4 spaces: "    job_state = C"
ATTR_RE = re.compile(r"^ {4}([A-Za-z_][\w.\-]*) = (.*)$")


def load_token():
    token = os.environ.get("GATEWAY_TOKEN", "").strip()
    token_file = os.environ.get("GATEWAY_TOKEN_FILE", "")
    if not token and token_file:
        with open(token_file) as fh:
            token = fh.read().strip()
    if not token:
        sys.exit("GATEWAY_TOKEN or GATEWAY_TOKEN_FILE must be set")
    return token.encode("utf-8")


TOKEN = load_token()


def run(argv, stdin_text=None, timeout=CMD_TIMEOUT):
    """Run a Torque command without a shell. Returns (returncode, stdout, stderr)."""
    kwargs = {}
    if stdin_text is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = stdin_text
    proc = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=timeout,
        **kwargs
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_qstat_full(output):
    attrs = {}
    for line in output.splitlines():
        match = ATTR_RE.match(line)
        if match:
            attrs[match.group(1)] = match.group(2).strip()
    return attrs


def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def simplify_status(attrs):
    """Map qstat -f attributes to COMPLETED / FAILED / RUNNING / QUEUED / UNKNOWN."""
    state = attrs.get("job_state")
    exit_status = parse_int(attrs.get("exit_status"))
    # exit_status is only set once the job has finished.
    if exit_status is not None:
        if exit_status == 0:
            return "COMPLETED"
        return "FAILED"
    if state == "C":
        return "COMPLETED"
    if state == "Q":
        return "QUEUED"
    if state is None:
        return "UNKNOWN"
    # R, E (still exiting), H, T, W, S
    return "RUNNING"


class Handler(BaseHTTPRequestHandler):
    server_version = "torque-gateway"
    sys_version = ""

    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            self._send(401, {"error": "unauthorized"})
            return False
        if not hmac.compare_digest(header[7:].strip().encode("utf-8"), TOKEN):
            self._send(401, {"error": "unauthorized"})
            return False
        return True

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length <= 0:
            self._send(400, {"error": "Content-Length required"})
            return None
        if length > MAX_BODY:
            self._send(413, {"error": "body too large"})
            return None
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            self._send(400, {"error": "invalid JSON"})
            return None
        if not isinstance(data, dict):
            self._send(400, {"error": "JSON object expected"})
            return None
        return data

    def _job_id(self):
        match = JOB_PATH_RE.match(self.path)
        if not match:
            self._send(404, {"error": "not found"})
            return None
        job_id = unquote(match.group(1))
        if not JOB_ID_RE.match(job_id):
            self._send(400, {"error": "invalid job id"})
            return None
        return job_id

    def do_GET(self):
        if self.path == "/health":
            return self._health()
        if not self._authorized():
            return
        job_id = self._job_id()
        if job_id is None:
            return
        self._status(job_id)

    def do_POST(self):
        if self.path != "/jobs":
            return self._send(404, {"error": "not found"})
        if not self._authorized():
            return
        data = self._read_json()
        if data is None:
            return
        script = data.get("script")
        if not isinstance(script, str) or not script.strip():
            return self._send(400, {"error": "script is required"})
        # Directives (#PBS -N, -d, -l) are inside the script. qsub gets no flags.
        try:
            code, out, err = run(["qsub"], stdin_text=script)
        except subprocess.TimeoutExpired:
            return self._send(504, {"error": "qsub timed out"})
        if code != 0:
            return self._send(502, {"error": "qsub failed", "detail": err.strip()[:500]})
        self._send(201, {"job_id": out.strip()})

    def do_DELETE(self):
        if not self._authorized():
            return
        job_id = self._job_id()
        if job_id is None:
            return
        try:
            code, out, err = run(["qdel", job_id])
        except subprocess.TimeoutExpired:
            return self._send(504, {"error": "qdel timed out"})
        if code != 0 and "Unknown Job Id" in err:
            return self._send(404, {"job_id": job_id, "status": "NOT_FOUND"})
        if code != 0 and "invalid for state" in err:
            return self._send(409, {"job_id": job_id, "error": "job state does not allow qdel"})
        if code != 0:
            return self._send(502, {"error": "qdel failed", "detail": err.strip()[:500]})
        self._send(200, {"job_id": job_id, "deleted": True})

    def _health(self):
        try:
            code, _, err = run(["qstat", "-q"], timeout=10)
        except subprocess.TimeoutExpired:
            return self._send(503, {"status": "degraded", "detail": "qstat timed out"})
        if code != 0:
            return self._send(503, {"status": "degraded", "detail": err.strip()[:200]})
        self._send(200, {"status": "ok"})

    def _status(self, job_id):
        try:
            code, out, err = run(["qstat", "-f", job_id])
        except subprocess.TimeoutExpired:
            return self._send(504, {"error": "qstat timed out"})
        if code != 0 and "Unknown Job Id" in err:
            # Never submitted, or purged after the server's keep_completed window.
            return self._send(404, {"job_id": job_id, "status": "NOT_FOUND"})
        if code != 0:
            return self._send(502, {"error": "qstat failed", "detail": err.strip()[:500]})
        attrs = parse_qstat_full(out)
        self._send(200, {
            "job_id": job_id,
            "status": simplify_status(attrs),
            "job_state": attrs.get("job_state"),
            "exit_status": parse_int(attrs.get("exit_status")),
            "exec_host": attrs.get("exec_host"),
        })


class ThreadedServer(ThreadingMixIn, HTTPServer):
    """HTTPServer plus a thread per request. The class owns the accept loop."""

    daemon_threads = True
    request_queue_size = 32


def main():
    server = ThreadedServer((HOST, PORT), Handler)
    print("torque-gateway listening on %s:%d" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
