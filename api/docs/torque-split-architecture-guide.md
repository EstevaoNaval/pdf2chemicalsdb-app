# Split Architecture: Modern Celery Worker + Legacy PBS Torque Gateway

> **This document is a guideline, not a mandatory step-by-step plan.**
> Adapt names, versions, networks and security choices to your environment and your organization's policies. Every file and command below is a model to be reviewed and tested before production use.

---

## 1. Assessment of the idea

I agree with separating the two services. In short:

**What you gain**

- **Independent lifecycles.** The Celery worker can use a current Python and current wheels. The legacy side (CentOS 7, glibc 2.17, Torque 6.1.3) only has to keep `qsub`/`qstat`/`qdel` working and can stay frozen.
- **A very small legacy surface.** The Torque container runs one small process written with the Python standard library, instead of a whole application stack on an end-of-life OS.
- **Horizontal scaling of workers.** In the previous design every worker container was a Torque submit host and needed its own hostname, static IP and trust entry on the server. Now only the gateway is registered, and you can run as many Celery workers as you want.
- **One place for Torque identity and trust.** The service user, `trqauthd`, `hosts.equiv` and the `ruserok` check concern a single container.

**What it costs**

- One more service, one more network hop and one more failure mode (gateway down, gateway slow).
- An API to secure. The gateway token is effectively the credential of the cluster service account (see section 13).
- Job submission over HTTP is **not idempotent**: a timeout after the request was sent can leave you not knowing whether the job exists (see section 11).
- Files are still a separate problem: the job script travels through the API, but the data that jobs read and write must live on storage visible to both the compute nodes and the worker (section 2).
- The gateway still runs on the Python 3.6 of CentOS 7 (standard library only). That is acceptable for an internal-only service, but it is a risk to be aware of (section 16).

---

## 2. Architecture overview

```
              project network 192.168.115.0/24 (nothing published to the host)

 +---------------------------+   HTTP + bearer token   +-------------------------------------+
 | celery-worker (N replicas)| ----------------------> | torque-gateway (1 instance)         |
 | modern Python (Debian)    |   POST   /jobs          | CentOS 7 + Torque 6.1.3 clients     |
 | no Torque, no NIS         |   GET    /jobs/<id>     | trqauthd (root) + gateway.py        |
 | app code + data group     |   DELETE /jobs/<id>     | runs as svc_pdf2chemicals_prod      |
 +-------------+-------------+                         | 192.168.115.11                      |
               |                                       +------------------+------------------+
               | broker                                                   | qsub / qstat / qdel
               v                                                          | (via trqauthd, port 15001)
        Celery broker                                                     v
                                                     pbs_server "feynman"  (trusts the gateway host)
                                                                          |
                                                          pbs_mom nodes run the jobs as
                                                          svc_pdf2chemicals_prod (NIS)
```

| | `celery-worker` | `torque-gateway` |
|---|---|---|
| Base image | `python:<version>-slim-bookworm` (official) | `centos:7` |
| Contains | Application code, venv | Torque 6.1.3 clients, `trqauthd`, `gosu`, `gateway.py` |
| Runs as | Unprivileged user (UID/GID chosen for data access) | Starts as root for `trqauthd`, then `svc_pdf2chemicals_prod` |
| Torque identity | None | Service user and group, same name/UID/GID as NIS |
| Registered on the Torque server | No | Yes (hostname + IP) |
| Replicas | Any number | One (static hostname/IP) |

**Data.** The gateway only handles job control (submit, status, cancel). Whatever your jobs read and write must be on a filesystem that the compute nodes can see (for example NFS), and the Celery worker should see the same location (a bind mount, with the `labsoa_website_backend_data` group as secondary group). The gateway does not move files.

---

## 3. Communication options

| Option | How it works | Strengths | Weaknesses | Verdict |
|---|---|---|---|---|
| **HTTP gateway** | A small API in the Torque container exposes submit, status and cancel | Explicit contract, no shell strings, typed errors, parsing of `qstat -f` lives in one place, easy to health-check and to test | A service to write, secure and maintain | **Recommended** |
| **SSH** | `sshd` in the Torque container, the worker runs `ssh gw qsub ...` | No custom code, mature authentication | Command strings and text parsing in the worker, key management, `sshd` plus `trqauthd` in one container, forced-command wrapper needed to limit what a key can do | Valid if you prefer zero custom code |
| **Legacy Celery worker on a dedicated queue** | A second Celery worker with an old Python consumes a `torque` queue | Reuses your broker, no new protocol | Needs an old Celery and an old Python on an EOL OS, which defeats the purpose of the split | Not recommended |
| **Docker socket / `docker exec`** | The worker runs commands in the Torque container through the Docker API | Simple | Access to the Docker socket is root on the host | Avoid |

Why HTTP: your application needs three operations and a stable answer to "what is the state of this job". An API that returns `COMPLETED`, `FAILED`, `RUNNING`, `QUEUED`, `NOT_FOUND` is a better contract than text from a remote command, and it moves the `qstat -f` parsing (and the `keep_completed` dependency) out of the application.

If you choose SSH instead, the Torque-side Dockerfile stays almost the same: add `openssh-server`, install the worker's public key with a `command="..."` restriction that only allows `qsub`, `qstat` and `qdel`, and make the entrypoint start `trqauthd` and then `sshd -D`. The Torque trust model (section 4) is identical.

---

## 4. How Torque authenticates submissions in this architecture

Torque 6.1.3 authenticates by **host and user**, not by password (see the Admin Guide; the default method relies on `trqauthd`, privileged ports and the `ruserok` check). The server decides whether `user@submit-host` is acceptable:

```
qsub (gateway, as svc_pdf2chemicals_prod)
  -> trqauthd (root, same container)
     -> pbs_server (feynman:15001)
          1. Does the user exist on the server?
          2. Is the user/group allowed by the queue ACLs?
          3. Is user@submit-host trusted? (ruserok: /etc/hosts.equiv, ~user/.rhosts)
             or is the host listed in submit_hosts?
          4. Optional extra restrictions (acl_hosts / acl_host_enable)
     -> pbs_mom (execution node): does the user exist there with the same UID/GID?
```

What this means for the split:

1. **Only the gateway is a Torque submit host.** Its hostname and IP are what the server must resolve and trust. The Celery worker never talks to Torque and needs no entry on the server.
2. **Identity lives in the gateway image.** The service user and group (same name, UID and GID as in NIS) are created there, so `getpwuid` yields the name the server expects. The server resolves the user from its own account database.
3. **`trqauthd` must run as root.** The gateway container starts as root only to launch `trqauthd`, then drops to the service user. `gateway.py` and every `qsub` it spawns run as `svc_pdf2chemicals_prod`.
4. **Trust entries.** Server side: a hosts entry (so the server can resolve the gateway name) and a bare-hostname line in `/etc/hosts.equiv`. The `submit_hosts` server attribute is documented by the Admin Guide as an alternative that does not use RCmd authentication, with a warning about DNS spoofing. MUNGE is a compile-time, credential-based alternative that is not used in this cluster.
5. **Hostname format.** The Admin Guide asks for fully qualified names in `hosts.equiv`. In the prototype a short name resolved through `/etc/hosts` worked. Avoid underscores in the gateway hostname (use a hyphen, for example `pdf2chemicals-torque-gw`), because underscores are not valid in standard host names.
6. **The trust boundary moves.** Before, whoever controlled a trusted container controlled the service account. Now it is whoever holds the **gateway token** and can reach the gateway on the network. Section 13 covers that.
7. **Network visibility.** Because the gateway and `pbs_server` run on the same Docker host, the server sees the gateway's own IP on the project network (traffic to the local host is not NATed). If the server were on another machine, outbound traffic would typically be masqueraded to the Docker host's IP, and that is the identity to register.

---

## 5. Repository layout

```
.
├── docker-compose.yml          # your EXISTING file, with the additions from section 9
├── .env                        # not committed; existing variables + the additions from section 9
├── secrets/
│   └── torque_gateway_token    # not committed
├── torque-gateway/
│   ├── Dockerfile
│   ├── docker-entrypoint.sh
│   ├── gateway.py              # reference implementation, delivered with this guide
│   └── vendor/
│       └── torque-6.1.3.tar.gz # same tarball used for the server
└── celery-worker/
    ├── Dockerfile
    ├── requirements.txt
    └── src/                    # your Celery application
```

Add `.git`, `.env`, `secrets/` and `**/__pycache__` to a `.dockerignore` in each build context (or at the repository root, depending on your layout).

---

## 6. Torque gateway service

### 6.1 Dockerfile

Based on the prototype image that worked: same Torque build (`make packages`, clients package with `--install`), `trqauthd` as root and `gosu` for the privilege drop. The Python build and the application venv from the previous CentOS 7 attempt are gone. The gateway only needs the Python 3.6 that CentOS 7 provides, because it uses only the standard library.

```dockerfile
# =============================================================================
# Torque gateway -- CentOS 7 + Torque 6.1.3 clients + HTTP gateway (gateway.py)
#
# Same Torque flow as the validated prototype (make packages -> clients package
# -> --install, trqauthd as root, privilege drop with gosu). No Python build:
# the gateway uses only the standard library of the Python 3.6 shipped by CentOS 7.
#
# Build context (./torque-gateway) must contain:
#   vendor/torque-6.1.3.tar.gz   same tarball used to install the server
#   gateway.py                   HTTP gateway
#   docker-entrypoint.sh         starts trqauthd as root, then drops to SVC_USER
#
# Build:
#   docker build \
#     --build-arg SVC_UID=<uid> --build-arg SVC_GID=<primary gid> \
#     --build-arg TORQUE_QUEUE_GID=<gid of torque_queue_batch> \
#     -t pdf2chemicals-torque-gateway ./torque-gateway
# =============================================================================
ARG TORQUE_VERSION=6.1.3

###############################################################################
# Stage 1: build Torque and produce the clients package
###############################################################################
FROM centos:7 AS torque-build
ARG TORQUE_VERSION
ARG TORQUE_SHA256=""
ARG TORQUE_CONFIGURE_OPTS=""

# CentOS 7 is EOL: point yum at the vault mirror
RUN sed -i -e 's|^mirrorlist=|#mirrorlist=|g' \
           -e 's|^#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' \
           /etc/yum.repos.d/CentOS-*.repo

# Build requirements from the 6.1.3 Admin Guide: libxml2-devel, openssl-devel, boost-devel,
# libtool, gcc, gcc-c++, make (autotools only used if the tarball has no ./configure)
RUN yum install -y make gcc gcc-c++ libtool autoconf automake which tar gzip \
        openssl-devel libxml2-devel boost-devel \
    && yum clean all

WORKDIR /src
COPY vendor/torque-${TORQUE_VERSION}.tar.gz /src/

# No --enable-cgroups: the guide requires it for pbs_server/pbs_mom, not for client commands.
# Plain `make` on purpose (parallel builds of Torque can be flaky).
RUN if [ -n "${TORQUE_SHA256}" ]; then \
      echo "${TORQUE_SHA256}  torque-${TORQUE_VERSION}.tar.gz" | sha256sum -c -; \
    fi \
 && tar xzf torque-${TORQUE_VERSION}.tar.gz \
 && cd torque-${TORQUE_VERSION} \
 && { [ -x ./configure ] || ./autogen.sh; } \
 && ./configure --prefix=/usr/local --with-server-home=/var/spool/torque ${TORQUE_CONFIGURE_OPTS} \
 && make \
 && make packages \
 && cp torque-package-clients-linux-*.sh /src/torque-clients.sh

###############################################################################
# Stage 2: runtime image
###############################################################################
FROM centos:7

# Identity must match the cluster (NIS): same names, UIDs and GIDs
ARG SVC_USER=svc_pdf2chemicals_prod
ARG SVC_UID
ARG SVC_GID
ARG TORQUE_QUEUE_GID
ARG GOSU_VERSION=1.17
ARG GOSU_SHA256=""

ENV SVC_USER=${SVC_USER} \
    GATEWAY_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:/usr/local/sbin:${PATH}"

RUN sed -i -e 's|^mirrorlist=|#mirrorlist=|g' \
           -e 's|^#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' \
           /etc/yum.repos.d/CentOS-*.repo

# Runtime libraries for the Torque clients + the system Python 3.6 used by the gateway
RUN yum install -y openssl-libs libxml2 python3 \
 && yum clean all

# gosu: drops privileges from root to the service user in the entrypoint
RUN curl -fsSL -o /usr/local/bin/gosu \
      "https://github.com/tianon/gosu/releases/download/${GOSU_VERSION}/gosu-$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')" \
 && if [ -n "${GOSU_SHA256}" ]; then echo "${GOSU_SHA256}  /usr/local/bin/gosu" | sha256sum -c -; fi \
 && chmod +x /usr/local/bin/gosu \
 && gosu --version

# Install the self-extracting clients package (Admin Guide 2.4.6) and register its libraries
COPY --from=torque-build /src/torque-clients.sh /tmp/torque-clients.sh
RUN chmod +x /tmp/torque-clients.sh \
 && /tmp/torque-clients.sh --install \
 && rm -f /tmp/torque-clients.sh \
 && echo /usr/local/lib > /etc/ld.so.conf.d/torque.conf \
 && ldconfig \
 && mkdir -p /var/spool/torque

# Fail the build now if a binary is missing or a shared library cannot be resolved
RUN set -e; \
    for b in qsub qstat qdel trqauthd; do \
      p="$(command -v "$b")" || { echo "ERROR: $b not found in PATH"; exit 1; }; \
      if ldd "$p" | grep -q "not found"; then echo "ERROR: missing libs for $b"; ldd "$p"; exit 1; fi; \
      echo "OK: $p"; \
    done; \
    python3 --version

# Service user: own primary group, plus torque_queue_batch as secondary group
RUN groupadd -g ${SVC_GID} ${SVC_USER} \
 && groupadd -g ${TORQUE_QUEUE_GID} torque_queue_batch \
 && useradd -m -u ${SVC_UID} -g ${SVC_GID} -G torque_queue_batch \
      -s /sbin/nologin ${SVC_USER}

# Gateway (root-owned, read-only for the service user)
COPY gateway.py /opt/gateway/gateway.py
RUN python3 -c "import ast; ast.parse(open('/opt/gateway/gateway.py').read())"

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
 && chmod +x /usr/local/bin/docker-entrypoint.sh

# Documentation only: nothing is published to the host. Reachable on the project network only.
EXPOSE 8080

# Do NOT set USER here: the entrypoint needs root to start trqauthd, then drops to ${SVC_USER}
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python3", "/opt/gateway/gateway.py"]
```

Notes:

- `TORQUE_SHA256` and `GOSU_SHA256` are optional integrity checks.
- The `ldd` guard fails the build if a Torque binary has an unresolved library.
- `EXPOSE 8080` is documentation only. Nothing is published to the host.
- If a UID or GID already exists in the CentOS 7 base image, `groupadd`/`useradd` fails: choose a free number.

### 6.2 Entrypoint

```bash
#!/bin/bash
set -euo pipefail

: "${TORQUE_SERVER_HOST:?TORQUE_SERVER_HOST must be set (server name, e.g. feynman)}"
: "${SVC_USER:?SVC_USER must be set}"

SPOOL=/var/spool/torque

# Point the Torque client commands to the server (read from $PBS_HOME/server_name)
mkdir -p "${SPOOL}"
echo "${TORQUE_SERVER_HOST}" > "${SPOOL}/server_name"

# Remove a stale socket left by a previous run of the same container (e.g. `docker restart`)
rm -f /tmp/trqauthd-unix

# trqauthd must run as root; it daemonizes and stays resident
if ! trqauthd; then
  echo "ERROR: trqauthd failed to start" >&2
  getent hosts "${TORQUE_SERVER_HOST}" >&2 || echo "ERROR: cannot resolve ${TORQUE_SERVER_HOST}" >&2
  exit 1
fi

# Wait up to ~10s for trqauthd (unix socket or loopback port 15005)
ready=0
for _ in $(seq 1 20); do
  if [ -S /tmp/trqauthd-unix ] || (exec 3<>/dev/tcp/127.0.0.1/15005) 2>/dev/null; then
    ready=1
    break
  fi
  sleep 0.5
done
if [ "${ready}" -ne 1 ]; then
  echo "ERROR: trqauthd did not become ready" >&2
  exit 1
fi

# Drop privileges: from here on, the gateway and every qsub/qstat/qdel run as the service user
exec gosu "${SVC_USER}" "$@"
```

- It fails fast if `trqauthd` does not start, so the restart policy and monitoring see the problem.
- `exec gosu ...` makes the gateway the main process, so signals from Docker reach it (together with `init: true`).

### 6.3 `gateway.py`

A reference implementation is delivered next to this guide (`torque-gateway/gateway.py`). It uses only the Python standard library and avoids features newer than Python 3.6 (no `capture_output`, no `text=`, no `ThreadingHTTPServer`).

Design points:

- **No shell.** Torque commands are run with `subprocess.run` and an argument list. The job script goes to `qsub` through stdin.
- **Allow-lists.** Job IDs, job names, queue names, resource strings and working directories are validated with strict regular expressions before they reach a command line.
- **Authentication.** Bearer token, compared in constant time. `GET /health` is the only unauthenticated endpoint.
- **Limits.** Maximum body size (default 1 MiB) and a timeout for every Torque command.
- **Status mapping.** The same rules as the earlier `qstat`-based status code: an `exit_status` means `COMPLETED` (0) or `FAILED` (any other value, including negative ones); `job_state` `C` means `COMPLETED`, `Q` means `QUEUED`, anything else `RUNNING`.

---

## 7. API contract

All bodies are JSON. Except `/health`, every request needs `Authorization: Bearer <token>`.

| Method and path | Purpose | Success | Errors |
|---|---|---|---|
| `GET /health` | Process is up and `qstat -q` works | `200 {"status": "ok"}` | `503` if Torque is unreachable |
| `POST /jobs` | Submit a job | `201 {"job_id": "57259.feynman"}` | `400` invalid input, `401`, `413` body too large, `502` qsub failed, `504` qsub timed out |
| `GET /jobs/<job_id>` | Job status | `200 {"job_id", "status", "job_state", "exit_status", "exec_host"}` | `404 {"status": "NOT_FOUND"}`, `401`, `502`, `504` |
| `DELETE /jobs/<job_id>` | Cancel a job | `200 {"job_id", "deleted": true}` | `404`, `409` (job state does not allow `qdel`), `401`, `502` |

`POST /jobs` body:

```json
{
  "script": "#!/bin/bash\nsleep 30\n",
  "name": "my-job",
  "queue": "batch",
  "resources": "nodes=1:ppn=2,walltime=01:00:00",
  "workdir": "/shared/path"
}
```

Only `script` is required. The other fields map to `qsub -N`, `-q`, `-l` and `-d`.

`status` is one of `COMPLETED`, `FAILED`, `RUNNING`, `QUEUED`, `UNKNOWN` (and the `404` answer carries `NOT_FOUND`).

**`NOT_FOUND`.** The server forgets finished jobs after its `keep_completed` window. The API reports that explicitly instead of guessing. The previous code treated an unknown job as `COMPLETED`. If you want that behavior, apply it in the Celery client (section 11), and persist the final status the first time you observe it.

---

## 8. Celery worker service

```dockerfile
# =============================================================================
# Celery worker -- modern Python on the official Debian-based image.
# No Torque binaries, no NIS identity: job control goes through the Torque
# gateway over HTTP (see the architecture guide).
#
# Build context (./celery-worker) must contain:
#   requirements.txt   dependencies of the Celery application (including celery and requests)
#   src/               Celery application
#
# Build:
#   docker build \
#     --build-arg APP_UID=<uid> --build-arg APP_GID=<gid> --build-arg DATA_GID=<gid> \
#     -t pdf2chemicals-celery ./celery-worker
# =============================================================================
ARG PYTHON_VERSION=3.12
ARG DEBIAN_RELEASE=bookworm

###############################################################################
# Stage 1: build the virtual environment (the full image has compilers and common -dev libraries)
###############################################################################
FROM python:${PYTHON_VERSION}-${DEBIAN_RELEASE} AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt

###############################################################################
# Stage 2: runtime
###############################################################################
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_RELEASE}

# The OS user does not need to match NIS for Torque any more (the worker never talks to Torque).
# It does need to be able to read/write the shared data folder: use a UID/GID that fits your data
# ownership, and the data group as secondary group.
ARG APP_USER=celery
ARG APP_UID
ARG APP_GID
ARG DATA_GROUP=labsoa_website_backend_data
ARG DATA_GID
# Runtime system libraries needed by your Python dependencies (e.g. "libxml2 libpq5")
ARG APP_RUNTIME_PACKAGES=""

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}"

RUN if [ -n "${APP_RUNTIME_PACKAGES}" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends ${APP_RUNTIME_PACKAGES} \
      && rm -rf /var/lib/apt/lists/*; \
    fi

RUN groupadd -g ${APP_GID} ${APP_USER} \
 && groupadd -g ${DATA_GID} ${DATA_GROUP} \
 && useradd -m -u ${APP_UID} -g ${APP_GID} -G ${DATA_GROUP} -s /usr/sbin/nologin ${APP_USER}

# Same path as in the builder stage, so the venv stays valid
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY src/ /app/

USER ${APP_USER}

# Replace <celery_app_module>. A `command:` in Compose overrides this CMD.
CMD ["celery", "-A", "<celery_app_module>", "worker", "--loglevel=INFO", "--concurrency=4"]
```

Notes:

- The worker has **no Torque binaries and no NIS identity**. Its OS user only has to be able to use the data folder, so pick `APP_UID`/`APP_GID` that fit your data ownership and keep `labsoa_website_backend_data` as a secondary group.
- Dependencies are installed in a builder stage that has compilers; the final image is the slim one. Add runtime system libraries through `APP_RUNTIME_PACKAGES` if your dependencies need them.
- `requirements.txt` must include `celery` and `requests` (used by the gateway client in section 11).
- The worker needs no `init`, no entrypoint and no root phase.

---

## 9. Compose: adapting your existing file

The snippets below are **additions to merge** into your existing Compose project. Do not define the network again.

### 9.1 `.env`: additions

Your existing network settings stay as they are. Note that each assignment must be on its own line.

```dotenv
# Service user (from `id svc_pdf2chemicals_prod` on the master)
SVC_PDF2CHEMICALS_PROD_USER=svc_pdf2chemicals_prod
SVC_PDF2CHEMICALS_PROD_UID=
SVC_PDF2CHEMICALS_PROD_GID=
TORQUE_QUEUE_GID=

# Torque server name (from /var/spool/torque/server_name on the master)
TORQUE_SERVER_HOST=feynman
# Address where pbs_server is reachable from the project network (Docker host, usually the network gateway):
#   docker network inspect <network> --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'
TORQUE_SERVER_IPV4=192.168.115.1

# Identity of the gateway on the network (registered on the Torque server)
TORQUE_GATEWAY_HOSTNAME=pdf2chemicals-torque-gw
TORQUE_GATEWAY_IPV4=192.168.115.11

# Celery worker (file access only)
CELERY_WORKER_UID=
CELERY_WORKER_GID=
DATA_GID=
DATA_DIR=

# Optional integrity check of the Torque tarball
TORQUE_SHA256=
```

Reserve `192.168.115.11` (and the worker's existing address) so that Docker cannot hand them to another container: give your other services static addresses or restrict the dynamic pool with `ipam` `ip_range` in the existing network definition.

### 9.2 Token

```bash
mkdir -p secrets
openssl rand -hex 32 > secrets/torque_gateway_token
chmod 0444 secrets/torque_gateway_token      # see the note below
```

Compose bind-mounts file-based secrets with the host file's permissions, so the file must be readable by both container users (the gateway's service user and the worker's user). Keep the `secrets/` directory itself restricted on the host and out of version control.

### 9.3 Services

```yaml
services:
  torque-gateway:
    build:
      context: ./torque-gateway
      args:
        SVC_USER: ${SVC_PDF2CHEMICALS_PROD_USER:-svc_pdf2chemicals_prod}
        SVC_UID: ${SVC_PDF2CHEMICALS_PROD_UID:?set SVC_PDF2CHEMICALS_PROD_UID in .env}
        SVC_GID: ${SVC_PDF2CHEMICALS_PROD_GID:?set SVC_PDF2CHEMICALS_PROD_GID in .env}
        TORQUE_QUEUE_GID: ${TORQUE_QUEUE_GID:?set TORQUE_QUEUE_GID in .env}
        TORQUE_SHA256: ${TORQUE_SHA256:-}
    image: pdf2chemicals-torque-gateway:${IMAGE_TAG:-latest}
    hostname: ${TORQUE_GATEWAY_HOSTNAME:?set TORQUE_GATEWAY_HOSTNAME in .env}   # the name the server will see
    init: true                                   # reaps zombies (trqauthd daemonizes)
    restart: unless-stopped
    environment:
      TORQUE_SERVER_HOST: ${TORQUE_SERVER_HOST:?set TORQUE_SERVER_HOST in .env}
      GATEWAY_TOKEN_FILE: /run/secrets/torque_gateway_token
    secrets:
      - torque_gateway_token
    networks:
      <your_existing_network>:
        ipv4_address: ${TORQUE_GATEWAY_IPV4:?set TORQUE_GATEWAY_IPV4 in .env}
    extra_hosts:
      # TORQUE_SERVER_HOST must be the server HOSTNAME (as in its server_name file), not an IP.
      - "${TORQUE_SERVER_HOST}:${TORQUE_SERVER_IPV4:?set TORQUE_SERVER_IPV4 in .env}"
    healthcheck:
      # Process is up and Torque is reachable as the service user
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:8080/health > /dev/null"]
      interval: 30s
      timeout: 15s
      retries: 3
      start_period: 30s
    # No `ports:`: the gateway is reachable only from the project network.

  <your_celery_worker_service>:                  # your EXISTING service: merge these keys
    build:
      context: ./celery-worker
      args:
        APP_UID: ${CELERY_WORKER_UID:?set CELERY_WORKER_UID in .env}
        APP_GID: ${CELERY_WORKER_GID:?set CELERY_WORKER_GID in .env}
        DATA_GID: ${DATA_GID:?set DATA_GID in .env}
    restart: unless-stopped
    stop_grace_period: 120s                      # let Celery finish its warm shutdown
    environment:
      TORQUE_GATEWAY_URL: http://torque-gateway:8080
      TORQUE_GATEWAY_TOKEN_FILE: /run/secrets/torque_gateway_token
    secrets:
      - torque_gateway_token
    depends_on:
      torque-gateway:
        condition: service_healthy
    volumes:
      - ${DATA_DIR:?set DATA_DIR in .env}:/data

secrets:
  torque_gateway_token:
    file: ./secrets/torque_gateway_token
```

Merge notes:

- **Remove from the worker** everything that existed only for Torque: `TORQUE_SERVER_HOST`, the `extra_hosts` mapping of the server, any `user:`/`entrypoint:` workaround. The worker no longer needs a trust entry, a static IP for Torque purposes, or access to the Torque server port.
- **`environment`:** if your service uses the list form (`- KEY=value`), use that form for the new entries. Do not mix list and mapping forms in one service.
- **Service DNS.** The worker reaches the gateway as `torque-gateway` (the Compose service name), which works on any network both services share.
- **`command:`** can stay as it is in your existing worker service.
- **No `ports:` and no `network_mode: host`** anywhere. The gateway needs to reach TCP 15001 on `TORQUE_SERVER_IPV4`. If the existing network is declared `internal: true`, verify that traffic to the host address is still possible in your environment.

---

## 10. Server-side registration

Run on the Torque server host, as root. The identity to register is the **gateway's** (hostname from `.env`, IP `192.168.115.11`).

1. **Make the gateway name resolvable (both directions).** Add to `/etc/hosts`:

   ```
   192.168.115.11  pdf2chemicals-torque-gw
   ```

   ```bash
   getent hosts pdf2chemicals-torque-gw
   getent hosts 192.168.115.11
   ```

2. **Trust the host for submission.** Add the **bare hostname** to `/etc/hosts.equiv`:

   ```
   pdf2chemicals-torque-gw
   ```

   This trusts the same-named user from that host, which is `svc_pdf2chemicals_prod`. Do not use the `host +` form.

3. **Alternative: `submit_hosts`.** Documented by the Admin Guide as a way to trust submit hosts without RCmd authentication. It was not tested in the prototype, and the guide warns that it is subject to DNS spoofing: use it only in controlled and trusted environments.

   ```bash
   qmgr -c "set server submit_hosts += pdf2chemicals-torque-gw"
   ```

4. **Clean up obsolete entries** from the earlier designs once the migration is done, from both `/etc/hosts` and `/etc/hosts.equiv` (for example `torque-client-proto` and `pdf2chemicals_worker`). Fewer trusted names is a smaller attack surface.

5. **Firewall.** In the prototype no firewall change was needed. If your host filters traffic from Docker networks, allow the project subnet to reach TCP 15001. Example for `firewalld`:

   ```bash
   firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.115.0/24" port port="15001" protocol="tcp" accept'
   firewall-cmd --reload
   ```

6. **Completed-job visibility**, needed for status checks after a job finishes:

   ```bash
   qmgr -c "set server keep_completed = 86400"
   ```

   Choose a value longer than the longest interval between two status polls of the same job.

---

## 11. Celery side: client and tasks

Replace every direct use of `qsub`, `qstat`, `qdel` and `tracejob` with calls to the gateway. Remove `TORQUE_USER_HOME`, the `sh -c "(cd ... && ...)"` wrapper and `shell=True`.

```python
# torque_gateway.py
import os
from urllib.parse import quote

import requests


class TorqueGatewayError(RuntimeError):
    pass


class TorqueGateway:
    def __init__(self, base_url=None, token_file=None, timeout=30):
        self.base_url = (base_url or os.environ["TORQUE_GATEWAY_URL"]).rstrip("/")
        token_file = token_file or os.environ.get(
            "TORQUE_GATEWAY_TOKEN_FILE", "/run/secrets/torque_gateway_token"
        )
        with open(token_file) as fh:
            token = fh.read().strip()
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"
        self._timeout = timeout

    def _job_url(self, job_id):
        return f"{self.base_url}/jobs/{quote(job_id, safe='')}"

    def submit(self, script, name=None, queue=None, resources=None, workdir=None):
        payload = {"script": script}
        for key, value in (("name", name), ("queue", queue),
                           ("resources", resources), ("workdir", workdir)):
            if value is not None:
                payload[key] = value
        resp = self._session.post(f"{self.base_url}/jobs", json=payload, timeout=self._timeout)
        if resp.status_code != 201:
            raise TorqueGatewayError(f"submit failed: {resp.status_code} {resp.text}")
        return resp.json()["job_id"]

    def status(self, job_id):
        """COMPLETED, FAILED, RUNNING, QUEUED, UNKNOWN or NOT_FOUND."""
        resp = self._session.get(self._job_url(job_id), timeout=self._timeout)
        if resp.status_code == 404:
            return "NOT_FOUND"
        if resp.status_code != 200:
            raise TorqueGatewayError(f"status failed: {resp.status_code} {resp.text}")
        return resp.json()["status"]

    def cancel(self, job_id):
        resp = self._session.delete(self._job_url(job_id), timeout=self._timeout)
        if resp.status_code not in (200, 404, 409):
            raise TorqueGatewayError(f"cancel failed: {resp.status_code} {resp.text}")
        return resp.status_code == 200
```

Example tasks:

```python
import requests
from celery import shared_task

from .torque_gateway import TorqueGateway


@shared_task(bind=True, autoretry_for=(requests.ConnectionError,), retry_backoff=True, max_retries=5)
def submit_job(self, script, name=None):
    # Retries only when the connection could not be established (the request was not sent).
    return TorqueGateway().submit(script, name=name)


@shared_task(bind=True, autoretry_for=(requests.ConnectionError, requests.Timeout),
             retry_backoff=True, max_retries=10)
def check_job(self, job_id):
    status = TorqueGateway().status(job_id)
    # Previous behavior: a job the server no longer knows was treated as COMPLETED.
    # It may also never have existed, so persist the final status as soon as you see it.
    return "COMPLETED" if status == "NOT_FOUND" else status
```

Points to keep in mind:

- **Submission is not idempotent.** `requests.ConnectionError` (connection not established) is safe to retry. A **read timeout** after the request was sent is ambiguous: the job may exist. Use unique job names (`name`) and check for an existing job before resubmitting, or persist a submission record before calling the gateway.
- **Status is safe to retry**, because it is read-only.
- **`NOT_FOUND`** means "unknown to the server now". It requires `keep_completed` (section 10). Persist terminal states in your own database when you first observe them.
- If you submit **job arrays** (`qsub -t`), the reference gateway does not handle them: each sub-job would need its own query. Review that before using arrays.

---

## 12. Build, run and validate

```bash
docker compose build torque-gateway <your_celery_worker_service>
docker compose up -d
docker compose ps          # gateway should become "healthy" before the worker starts
docker compose logs torque-gateway
```

1. **Torque from the gateway container, as the service user:**

   ```bash
   docker compose exec -u svc_pdf2chemicals_prod torque-gateway bash -c '
     id
     qstat --version
     qstat -q
     echo "sleep 30" | qsub
     qstat'
   ```

2. **The API, from inside the gateway container:**

   ```bash
   docker compose exec torque-gateway sh -c '
     TOKEN=$(cat /run/secrets/torque_gateway_token)
     curl -s http://127.0.0.1:8080/health; echo
     curl -s -H "Authorization: Bearer $TOKEN" -X POST http://127.0.0.1:8080/jobs \
          -d "{\"script\": \"#!/bin/bash\\nsleep 30\\n\", \"name\": \"gw-test\"}"; echo'
   ```

3. **The worker reaching the gateway** (adjust the import to your package):

   ```bash
   docker compose exec <your_celery_worker_service> python -c \
     "from <your_package>.torque_gateway import TorqueGateway; print(TorqueGateway().status('<job_id>'))"
   ```

Checklist:

- [ ] The gateway image builds from the local tarball and the `ldd` guard passes.
- [ ] `id` shows the service user with group `torque_queue_batch`.
- [ ] `qstat --version` matches the server (6.1.3).
- [ ] `qsub` returns a job ID ending with the server name (`<id>.feynman`).
- [ ] `GET /health` returns `200`, and `401` without a token on the other endpoints.
- [ ] `POST /jobs` returns `201`, and `GET /jobs/<id>` shows `COMPLETED` with `exit_status` 0 after the job ends.
- [ ] The worker container is running and can reach the gateway, with no Torque tools inside it.
- [ ] No mounts of `/etc/passwd`, `/etc/group` or `/opt/torque` remain in any Compose file, and no `ports:` publish the gateway.
- [ ] Obsolete trust entries were removed from the server (section 10, step 4).

---

## 13. Security notes

- **The token is powerful.** Anyone with the gateway token and network access to the gateway can submit arbitrary job scripts to the cluster as `svc_pdf2chemicals_prod`. That is the purpose of the service, so treat the token like the account's credential: keep it out of version control and images, use a secret (not a plain environment variable, which shows in `docker inspect`), and rotate it by updating the file and restarting both services.
- **Network isolation.** Publish nothing to the host. Limit who can start containers on the project network, because the gateway's identity on the Torque side is host-based trust and anything on that network can try to reach the API.
- **Plain HTTP.** Inside a private Docker network this may be acceptable. If your policy requires encryption in transit, put a TLS-terminating proxy in front (mutual TLS if you want client authentication), or use SSH as the transport.
- **Least privilege.** The gateway runs as the service user, not root (only `trqauthd` runs as root). The gateway code is root-owned and read-only for the service user. Keep the service account's queue access minimal.
- **Input handling.** The gateway never builds shell commands and validates every field that reaches a command line. Keep it that way if you extend it (for example, to allow only certain queues or resource limits).
- **Logging hygiene.** The default HTTP log lines contain the request line but not the token or the script. Do not add logging of request bodies (job scripts may contain sensitive data).
- **`hosts.equiv`.** Use the bare hostname only. Never `host +`.

---

## 14. Operations

- **Scaling.** Run as many worker replicas as you need. The gateway is a single instance by design (static hostname and IP registered on the server). If it becomes a bottleneck, raise its concurrency limits first; running a second gateway means a second hostname, IP and trust entry.
- **Gateway availability.** Because workers wait for a healthy gateway, a gateway outage pauses job control but not the rest of your application. Use retries (section 11) and monitor `/health`.
- **Changing the gateway hostname or IP.** Update `.env`, the server's `/etc/hosts` and `/etc/hosts.equiv` together.
- **Torque version upgrades.** Replace the tarball in `torque-gateway/vendor/`, update `TORQUE_SHA256` and rebuild. Keep client and server versions aligned.
- **Rebuilds.** Rebuild both images periodically (the worker image receives Debian and Python updates). The CentOS 7 image receives no OS updates, since the distribution is end-of-life.
- **Token rotation.** Replace `secrets/torque_gateway_token` and recreate both services.

---

## 15. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `POST /jobs` returns `502` with `ruserok failed validating ...` | The server does not trust the gateway host | Check `/etc/hosts` and `/etc/hosts.equiv` on the server. Trust the exact name printed after `from`. Check the hostname format (section 4, item 5) |
| `502` with `Unauthorized Request` | Queue ACL or host restrictions | `qmgr -c "p q batch"` and `qmgr -c "p s"`; check `acl_hosts`, `acl_host_enable` and group ACLs |
| Gateway container exits right after start | `trqauthd` failed, wrong `server_name`, CRLF in the entrypoint, or missing `.env`/token | `docker compose logs torque-gateway`; check name resolution of `TORQUE_SERVER_HOST` |
| Gateway is `unhealthy` | `qstat -q` fails inside the container | `docker compose exec -u svc_pdf2chemicals_prod torque-gateway qstat -q`; check `extra_hosts`, the server address and the firewall for TCP 15001 |
| `401` from the API | Token mismatch or missing header | Compare the secret file seen by both containers; check `Authorization: Bearer ...` |
| Worker cannot reach the gateway | Different networks or wrong URL | The worker and the gateway must share a network; use `http://torque-gateway:8080` |
| Worker cannot read the token | Secret file permissions on the host | Make the host file readable by both container users (section 9.2) |
| `qsub` works but the job never starts or runs as the wrong user | User or UID/GID mismatch on the execution node | `id svc_pdf2chemicals_prod` on the master and on a MOM must match the gateway image |
| `GET /jobs/<id>` returns `404` for a finished job | Job purged after `keep_completed` | Increase `keep_completed` and persist the final status in the application |
| Build fails in `configure` or `make` | Toolchain or dependency issue | This is the flow validated in the prototype on CentOS 7. Compare with the prototype image and read the first error |
| Build guard reports `not found` libraries | Runtime library missing in the final stage | Add the package that provides it to the `yum install` of stage 2 |

Server-side debugging while reproducing the problem:

```bash
tail -f /var/spool/torque/server_logs/$(date +%Y%m%d)
```

---

## 16. Status and limitations

What was verified when this guide was written:

- `gateway.py` was exercised locally against **fake** `qsub`, `qstat` and `qdel` commands: authentication (`401`), input validation, status mapping (completed, failed, negative exit status, running, queued, unknown job), submit with all options, cancel (including `409` and `404`), request size limit (`413`) and missing `Content-Length` (`400`). That test ran on Python 3.12, **not** on Python 3.6, and **not** against a real Torque server.
- The two Dockerfiles, the entrypoint and the Compose snippets have **not been built or run**. The Torque part reuses the flow that worked in the prototype, but the clients-only image, the gateway process and the healthcheck have not been validated.

Limitations to weigh:

- **Python 3.6 is end-of-life**, and the standard-library `http.server` is not hardened for hostile networks. The mitigation in this design is isolation (private network, token, no published ports). If you need stronger guarantees, rewrite the gateway as a static binary (for example in Go) or put it behind a hardened reverse proxy.
- **No TLS** in the reference setup.
- **No idempotency** for submissions (section 11).
- **No job-array support** in the reference gateway.
- **Job stdout/stderr handling** and result storage are out of scope of this guide.
- **CentOS 7** is listed as supported by Torque 6.1.3, but the OS itself no longer receives updates.

Remember: this is a guideline. Review each section against your environment, validate the gateway image in a non-production setting first, and adapt the security choices to your organization's requirements.
