# Production Guide: Celery Worker Container Submitting Jobs to PBS Torque 6.1.3 as a Service User

> **This document is a guideline, not a mandatory step-by-step plan.**
> Adapt names, paths, versions, networks and security choices to your environment and your organization's policies. Every command and file below is a model to be reviewed and tested before production use.

## This repo

The worker service `pdf2chemicals-celery-worker` follows this guide with these differences:

- The worker image is chosen with `PDF2CHEMICALS_WORKER_DOCKERFILE`. Default is `api/Dockerfile.ubuntu` (same OS family as the PBS host, Python 3.12). Alternatives are `api/Dockerfile.debian` and `api/Dockerfile.rocky`. Django-api and django-worker keep `api/Dockerfile`. Build context is `api`. Run Compose with `docker compose --env-file api/.env`.
- Application workdir is `/src`. Celery command is `-A labsoa_website_backend worker --queues=pdf2chemicals_tasks --prefetch-multiplier=1 --autoscale=3,0 --max-tasks-per-child=1 --loglevel=INFO`.
- The service user's primary group is `torque_queue_batch`. Supplementary group is `DATA_GROUP` / `DATA_GID` (`labsoa_website_backend_data`, `1844`) so the process can write `DATA_ROOT_DIR`.
- `qsub` is called as `qsub -d "$TORQUE_USER_HOME" <script>`. The PBS template runs `cd $PBS_O_WORKDIR`, and that directory must exist on the MOM. `TORQUE_USER_HOME` is a path, not a mount.
- `server_name` is written from `TORQUE_SERVER` (`feynman`). `extra_hosts` maps that name to `TORQUE_GATEWAY_IPV4` (the project-network gateway, not `172.17.0.1`). Fill `TORQUE_GATEWAY_IPV4` from `docker network inspect`.
- `get_pbs_job_status` and `is_pbs_job_completed` live in `api/pdf2chemicals_service/cluster.py`. There is no `pbs_job_status.py`. `pbsnodes | awk` is unchanged.
- The tarball is `api/vendor/torque-6.1.3.tar.gz` and is gitignored. `TORQUE_SHA256` in `api/.env` is optional.
- Hostname stays `pdf2chemicals_worker`. Register that name on the server in `/etc/hosts` and `/etc/hosts.equiv`, and set `keep_completed = 86400`, before relying on `qsub`.

---

## 1. Scope and status

### Goal

Run a **Celery worker** inside a Docker container (orchestrated by Docker Compose) that submits and manages PBS Torque jobs (`qsub`, `qstat`, `qdel`, ...) as the dedicated service user `svc_pdf2chemicals_prod`, **without depending on the Docker host** for identity or binaries.

Workarounds this guide removes:

| Previous workaround | Replacement |
|---|---|
| Mounting the host's `/etc/passwd` and `/etc/group` into the container | The service user and group are created inside the image, with the same name, UID and GID as in the cluster |
| `sh -c "(cd $TORQUE_USER_HOME && qsub ...)"` with a personal account | The Celery process itself runs as `svc_pdf2chemicals_prod` and calls `qsub` directly |
| Torque binaries or `/opt/torque` from the host | Torque 6.1.3 client binaries built into the image from the same tarball used by the server |
| `tracejob` (needs the server's log files) | `qstat -f` (queries the server over the network) |

### How this guide relates to your existing Compose project

The Compose content in this guide is **not a standalone stack**. It is a set of additions to be merged into your **existing** `docker-compose.yml`, which already defines the project network (`192.168.115.0/24`) and the Celery worker service (hostname `pdf2chemicals_worker`, IPv4 `192.168.115.10`, both taken from `.env`). See section 9.

### What was validated in the prototype

- A user-defined Docker bridge network with a static subnet and a static container IP.
- `qsub`, `qstat`, `qstat -f` and `pbsnodes` from a container as the service user, against the Torque 6.1.3 server running on the Docker host.
- Host trust through `/etc/hosts.equiv` (bare hostname, no `+`), plus a hosts entry on the server.
- The identity model: the service user published through NIS, and recreated in the image with the same name, UID and GID.
- The prototype image used **CentOS 7** and the `make packages` flow (clients package installed with `--install`).

### What is **not** validated yet (review carefully)

- **Any build on Debian.** This guide uses Debian, as the official Python images do, but the image has **not been built or run** by the author of this guide. Torque 6.1.3 is a 2018 code base and its vendor-supported operating systems do not include any current distribution (section 5). Expect to iterate on the first build.
- The clients-only build flow used here (`--disable-server --disable-mom` and a staged `make install`), which differs from the `make packages` flow validated in the prototype.
- The Celery integration (worker as service user, healthcheck, shutdown behavior).
- Values that depend on your environment (broker, Python version, network name, gateway).

### Out of scope

Handling and lifecycle of job stdout/stderr output files, and database design for job results.

---

## 2. Architecture overview

```
 Docker host (also runs pbs_server "feynman")
 +------------------------------------------------------------------+
 |                                                                  |
 |   existing project network 192.168.115.0/24                      |
 |   +----------------------------------------------+               |
 |   | celery worker "pdf2chemicals_worker"         |               |
 |   | 192.168.115.10                               |               |
 |   |                                              |               |
 |   |  entrypoint (root)                           |               |
 |   |    |- writes /var/spool/torque/server_name   |               |
 |   |    |- starts trqauthd (root)                 |               |
 |   |    `- exec gosu svc_pdf2chemicals_prod       |               |
 |   |         celery worker                        |               |
 |   |           `- qsub/qstat/qdel                 |               |
 |   |                |                             |               |
 |   |                `--> trqauthd (local) --------+----> pbs_server :15001
 |   +----------------------------------------------+               |
 +------------------------------------------------------------------+
                                                       |
                                  pbs_server --> pbs_mom (feynman4, ...)
                                  runs the job as svc_pdf2chemicals_prod (NIS)
```

---

## 3. How Torque authenticates submissions from other hosts

This section follows the Torque 6.1.3 Administrator Guide (installation and configuration chapters) and what was observed in the prototype.

### 3.1 The model: host-based trust, not passwords

By default, a Torque client does **not** present a password, token or key. The server trusts a request because of **where it comes from** and **which user name it reports**:

- **The local authorization agent.** Client commands (`qsub`, `qstat`, `qdel`, ...) talk to `trqauthd` on the same host. The Admin Guide describes `trqauthd` as the daemon that authorizes user connections to `pbs_server`. It **must run as root**, and it must be running on every host where client commands execute.
- **Privileged ports.** The default mechanism relies on privileged (reserved) ports plus the `ruserok` check: only root can bind such ports, so a connection from one tells the server it comes from a trusted root-owned daemon on that host. (The Admin Guide documents options such as `--disable-privports` and `--with-reserved-port-start` for this mechanism, and states that building with MUNGE disables the privileged-port `ruserok` method.)
- **The user name.** It comes from the **client's** account database, via the UID of the process that called `qsub`.

Because trust is based on host identity, **the integrity of the host name and IP is part of your security model** (see 3.6).

### 3.2 Path of a submission

```
qsub (as svc_pdf2chemicals_prod, in the container)
  -> trqauthd (root, same container)
     -> pbs_server (feynman:15001)
          1. Does the user exist on the server?
          2. Is the user/group allowed by the queue ACLs?
          3. Is user@submit-host trusted? (ruserok: /etc/hosts.equiv, ~user/.rhosts)
             or is the host listed in submit_hosts?
          4. Optional extra restrictions (acl_hosts / acl_host_enable)
        -> job accepted, job ID returned (e.g. 57259.feynman)
     -> pbs_server -> pbs_mom (execution node)
          5. Does the user exist on the execution node, with the same UID/GID?
```

### 3.3 The checks and where each one lives

| Check | Where it is configured | In this cluster |
|---|---|---|
| Local authorization agent | `trqauthd` in the container (root) and the `server_name` file | Started by the container entrypoint |
| User exists on the server | The server's account database | Local files on the master, published to the nodes via NIS |
| Queue ACLs | `qmgr -c "p q batch"` (`acl_groups`, `acl_users`, ...) | Service user belongs to `torque_queue_batch`; confirm how your queue is gated |
| **Host/user trust (RCmd / `ruserok`)** | `/etc/hosts.equiv` on the machine running `pbs_server`, or other R* authorization methods such as `~user/.rhosts` | **`hosts.equiv` with the bare hostname worked.** A `.rhosts` file did not work in the prototype (cause not diagnosed) |
| **Alternative: `submit_hosts`** | `qmgr -c "set server submit_hosts += <host>"` | Documented by the Admin Guide as a way to trust submit hosts **without** RCmd authentication. Not used or tested in the prototype |
| Name resolution of submit hosts | `/etc/hosts`, DNS or NIS, **on the server** | The Admin Guide requires each node and the server to resolve the names of every host they interact with. Here: a hosts entry for the worker |
| Extra host restrictions | `acl_hosts`, `acl_host_enable` (server or queue) | Optional |
| User on the execution node | The MOM's account database | NIS |

Observation from the prototype: `qstat` and `pbsnodes` worked **before** the container was trusted, while `qsub` was rejected with `Bad UID for job execution MSG=ruserok failed validating <user>/<user> from <hostname>`. The server had already resolved the user correctly; what failed was the host trust. The Admin Guide has an FAQ entry for this message (section 13.9.7 in the 6.1.3 guide).

**Notes from the Admin Guide on `hosts.equiv`:**

- The exact semantics depend on the operating system's `ruserok` (see its man page).
- The guide states that a hostname must be the **fully qualified** domain name. In the prototype, a short name resolved through `/etc/hosts` worked. If it does not work for you, use an FQDN consistently in the container hostname, the server's hosts entry and `hosts.equiv`.
- A line with only a hostname trusts the same-named user from that host. `host +` trusts any user from that host. A leading `+` cannot be attached to a user or host name (for example `+node02 user1` does not work).

**Notes on the alternatives:**

- **`submit_hosts`:** the Admin Guide warns that it is subject to DNS spoofing and should not be used outside controlled and trusted environments.
- **MUNGE:** a credential-based alternative. It is a **compile-time** choice (`--enable-munge-auth`), requires the same MUNGE version and a running MUNGE daemon on the server and on all submission hosts, and verifies `user@host` against `authorized_users` in the server database. Only one method can be active at a time, and enabling MUNGE disables the privileged-port `ruserok` method. This cluster uses `ruserok`, so the clients built in this guide use the default method.

### 3.4 How this applies to the containerized Celery worker

1. **Identity.** The service user and group exist in the image with the same name, UID and GID as in the cluster (section 7). `getpwuid` in the container then yields the name the server expects. The server resolves that name from its own account database; nothing is borrowed from the host.
2. **`trqauthd` as root, Celery as the service user.** The container starts as root only long enough to start `trqauthd`, then drops privileges (section 8). Celery and every `qsub` it spawns run as the service user. This is also why `USER` is not set in the Dockerfile.
3. **The container is a distinct submit host.** For Torque, a container is just another host. It needs a stable name and a stable IP so the server can resolve and trust it. Your existing network already provides this: hostname `pdf2chemicals_worker`, IPv4 `192.168.115.10`.
4. **Trust entries on the server.** The worker's hostname is registered in the server's `/etc/hosts` (so the server can resolve it) and in `/etc/hosts.equiv` (so `ruserok` accepts it) (section 10).
5. **Server name.** The container's `server_name` file contains the server's real name (`feynman`), so job IDs (`57259.feynman`) and the client's idea of the server match. The name is mapped to the Docker host's address on the project network with `extra_hosts`.

### 3.5 Different-host scenarios

| Scenario | What the server sees | What to register |
|---|---|---|
| `pbs_server` runs on the **same Docker host** (this cluster) | The container's own IP on the project network (traffic to the local host is not NATed) | The container's hostname and static IP |
| `pbs_server` is on **another machine** | Outbound container traffic is typically masqueraded to the Docker host's IP, so the container's own IP is invisible. Source-port rewriting by NAT could also matter for a privileged-port mechanism (not tested) | The Docker host's identity; all containers on that host look the same to the server. The error message of a failed `qsub` names the host the server is validating, which is the name to trust |
| **Several** Docker hosts or replicas | Each is a different host | One trust entry per distinct submit host name |

### 3.6 Security implications

- Anything that can present itself to the server as the trusted host name or IP can submit as the trusted user. Keep the Torque network private, and limit who can start containers on the network that holds the worker. Your project network is shared with other services, so a compromised container with network privileges on that subnet is a risk worth considering.
- Use the **bare hostname** form in `/etc/hosts.equiv`. A line such as `host +` trusts any user from that host and should not be used.
- The trusted identity is a single service user. Keep that account's privileges and queue access minimal.
- Keep forward and reverse resolution of the worker name consistent on the server.

---

## 4. Prerequisites and values to collect

Cluster-side steps (service user created in NIS, member of `torque_queue_batch`, visible on the server and on all MOMs) are assumed done.

| Value | How to obtain | Used in |
|---|---|---|
| Service user name | `svc_pdf2chemicals_prod` | `SVC_USER` build arg |
| UID | `id svc_pdf2chemicals_prod` on the master | UID build arg |
| Primary GID (`torque_queue_batch`) | same command | GID build arg |
| Server name | `cat /var/spool/torque/server_name` on the master (e.g. `feynman`) | `TORQUE_SERVER_HOST` |
| Torque tarball | The `torque-6.1.3.tar.gz` already used to install the server | `vendor/` folder |
| Existing network name and gateway | `docker network ls`; `docker network inspect <network>` | Compose merge, `extra_hosts` |
| Worker hostname and IP | Already in your `.env` (`pdf2chemicals_worker`, `192.168.115.10`) | Compose, server registration |
| Celery application module and Python version | From your project | `CMD`, `PYTHON_VERSION` |

The spool directory used in this guide is `/var/spool/torque`. If your server was built with a different `--with-server-home`, change it consistently in the Dockerfile and the entrypoint.

---

## 5. Base image choice

### Is a RHEL-family distribution required?

**No.** The Torque 6.1.3 Administrator Guide lists CentOS 6 and 7, RHEL 6 and 7, Scientific Linux 6 and 7, and SUSE Linux Enterprise Server 12 as supported operating systems. That list is a statement about **vendor support**, not a technical prohibition, and it is the same situation for every current base image: Rocky/Alma 8 and 9, Debian, Ubuntu and Alpine are all outside it. (The guide's own example output shows Torque on an Ubuntu system, and it includes an FAQ entry about building on Ubuntu, so Debian-family builds are not unusual. That is not a guarantee for version 6.1.3.)

The practical question is therefore which current base is **most likely to build and run** a 2018 code base. That cannot be settled by documentation alone, which is why the build includes a check that fails early (section 7).

### Options

| Option | Assessment |
|---|---|
| **Debian (`python:<version>-slim-bookworm`)** (recommended) | glibc-based, uses the official Python images (no separate Python installation), and `gosu` is available through `apt`. Bookworm ships gcc 12 and OpenSSL 3.0, the older of the two current Debian toolchains, which is the lower-risk choice for an old source tree. |
| Debian 13 "trixie" | Current stable release, with a longer support horizon. Newer compiler (gcc 14, stricter about old C constructs) and some library package names changed (for example `libssl3t64`). Worth trying once the bookworm build is working. |
| Ubuntu LTS | Same family and similar trade-offs as Debian. Fine if your organization standardizes on it. |
| Alpine (musl) | **Not recommended.** Torque 6.1.3 was written against glibc and I expect it to need patches on musl (unverified). In addition, Python wheels for scientific and document-processing libraries are often unavailable for musl, which can force slow source builds. Check your `requirements.txt` before considering it. |
| Rocky / Alma 8 | Closest to the CentOS 7 toolchain that the prototype validated, but not on the vendor's supported list either. A reasonable fallback if Debian builds fail. |

### Debian lifecycle (as of November 2026)

- Debian 12 "bookworm": regular security support ended on 12 July 2026, and the Debian LTS Team has taken over security support, which runs until 30 June 2028. Not every package is covered by LTS, so check what your image actually needs (the `debian-security-support` package can identify unsupported packages).
- Debian 13 "trixie" is the current stable release (released on 9 August 2025).

Source for these dates: the Debian project's announcement of 12 July 2026 and its release lifecycle information. Confirm them before relying on them for compliance decisions.

A pragmatic path: build and validate on bookworm now, then evaluate trixie before the LTS window closes.

### Notes

- **Build and run on the same Debian release.** A binary built on one release and run on another can fail on shared libraries (for example OpenSSL 1.1 versus 3). The Dockerfile uses the same `DEBIAN_RELEASE` for both stages.
- **Clients only.** Per the Admin Guide's configure options, `--disable-server` (no server and scheduler) and `--disable-mom` (no MOM daemon) are available. The image only needs the client commands and `trqauthd`, so the build skips the server and MOM code. That removes the largest part of the compilation (and the cgroups/hwloc requirements, which the guide ties to the server and MOM) and reduces build risk on a newer toolchain.
- **Compiler strictness.** The Admin Guide documents `--enable-gcc-warnings` ("if using gcc, default is to error on any warning"). The Dockerfile passes `--disable-gcc-warnings` so that warnings from a newer compiler do not stop the build. Remove it if your configure rejects it.
- **If the first build fails.** Read the first error. A missing dependency means adding a `-dev` package to the build stage and the matching runtime library to the final stage. If the staged-install flow misbehaves, the fallback is the flow validated in the prototype: configure without `--disable-server --disable-mom`, run `make` and `make packages`, and install `torque-package-clients-linux-*.sh` with `--install` in the final stage.

---

## 6. Repository layout

```
.
├── Dockerfile
├── docker-entrypoint.sh
├── docker-compose.yml        # your EXISTING file, with the additions from section 9
├── requirements.txt
├── .env                      # not committed; your existing file plus the additions from section 9
├── .dockerignore
├── vendor/
│   └── torque-6.1.3.tar.gz   # same tarball used for the server
└── src/                      # your Celery application
```

`.dockerignore`:

```
.git
.env
**/__pycache__
```

Handle the tarball according to your policy (Git LFS, internal artifact store, or committed). Record its SHA-256 and pass it as `TORQUE_SHA256` so the build verifies it.

---

## 7. Dockerfile

```dockerfile
ARG PYTHON_VERSION=3.12
ARG DEBIAN_RELEASE=bookworm
ARG TORQUE_VERSION=6.1.3

###############################################################################
# Stage 1: build the Torque CLIENTS (no server, no MOM) from the local tarball
###############################################################################
FROM debian:${DEBIAN_RELEASE}-slim AS build
ARG TORQUE_VERSION
ARG TORQUE_SHA256=""
ENV DEBIAN_FRONTEND=noninteractive

# Build requirements: compiler toolchain, libtool/autotools, OpenSSL and libxml2 headers, Boost headers.
# (Autotools are only used if the tarball has no ./configure.)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential libtool autoconf automake pkg-config \
      libssl-dev libxml2-dev libboost-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY vendor/torque-${TORQUE_VERSION}.tar.gz /src/

# Clients only: --disable-server (no server/scheduler) and --disable-mom (no MOM daemon).
# --disable-gcc-warnings avoids build failures caused by warnings from a newer compiler.
# Plain `make` on purpose (parallel builds of Torque can be unreliable).
RUN if [ -n "${TORQUE_SHA256}" ]; then \
      echo "${TORQUE_SHA256}  torque-${TORQUE_VERSION}.tar.gz" | sha256sum -c -; \
    fi \
 && tar xzf torque-${TORQUE_VERSION}.tar.gz \
 && cd torque-${TORQUE_VERSION} \
 && { [ -x ./configure ] || ./autogen.sh; } \
 && ./configure --prefix=/usr/local --with-server-home=/var/spool/torque \
      --disable-server --disable-mom --disable-gcc-warnings \
 && make \
 && make install DESTDIR=/stage

###############################################################################
# Stage 2: runtime image (official Python image + Torque clients + Celery application)
###############################################################################
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_RELEASE}

# Must match the service user in the cluster (NIS): same name, UID and GID
ARG SVC_USER=svc_pdf2chemicals_prod
ARG SVC_UID
ARG SVC_GID

ENV SVC_USER=${SVC_USER} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/sbin:${PATH}"

# Runtime libraries for the Torque clients (Debian 12 package names; they differ on Debian 13),
# plus gosu to drop privileges in the entrypoint.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libssl3 libxml2 gosu \
 && rm -rf /var/lib/apt/lists/*

# Torque clients staged by `make install DESTDIR=/stage`
COPY --from=build /stage/ /
RUN echo /usr/local/lib > /etc/ld.so.conf.d/torque.conf \
 && ldconfig \
 && mkdir -p /var/spool/torque

# Fail the build now if a binary is missing or a shared library cannot be resolved
RUN set -e; \
    for b in qsub qstat qdel trqauthd; do \
      p="$(command -v "$b")" || { echo "ERROR: $b not found in PATH"; exit 1; }; \
      if ldd "$p" | grep -q "not found"; then echo "ERROR: missing libs for $b"; ldd "$p"; exit 1; fi; \
      echo "OK: $p"; \
    done

# Service user, identical to the one published by NIS
RUN groupadd -g ${SVC_GID} torque_queue_batch \
 && useradd -m -u ${SVC_UID} -g ${SVC_GID} -s /usr/sbin/nologin ${SVC_USER}

# Application (code is owned by root and read-only for the service user)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

WORKDIR /app
COPY src/ /app/

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
 && chmod +x /usr/local/bin/docker-entrypoint.sh

# Do NOT set USER here: the entrypoint needs root to start trqauthd, then drops to ${SVC_USER}
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Replace <celery_app_module> with your Celery application (for example: myproject.celery_app).
# If your Compose service already defines `command:`, that command is used instead.
CMD ["celery", "-A", "<celery_app_module>", "worker", "--loglevel=INFO", "--concurrency=4"]
```

Notes:

- The Celery application, its dependencies and the Python version are placeholders for your project. If a dependency needs system libraries or compilation, add them to the runtime stage with `apt-get`.
- `TORQUE_SHA256` is optional; set it to enforce an integrity check of the tarball.
- If the UID or GID you need already exists in the base image, `groupadd`/`useradd` fails. Pick a base without the conflict or remove the conflicting entry.
- Celery refuses to run as root by default. Running it as the service user is therefore both a Torque requirement (identity) and a Celery best practice.

---

## 8. Entrypoint

`docker-entrypoint.sh`:

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

# Drop privileges: from here on, Celery and every qsub/qstat run as the service user
exec gosu "${SVC_USER}" "$@"
```

Why this design:

- `exec gosu ...` makes the command (Celery) the main process, so signals from Docker reach it (together with `init: true` in Compose).
- The entrypoint wraps **whatever command** the container runs, including a `command:` defined in your existing Compose service.
- It fails fast when `trqauthd` does not start, so the restart policy and your monitoring see the problem.

---

## 9. Compose: adapting your existing file

The snippets below are **additions to merge** into your existing Compose project. Do not define the network again: the project network (`192.168.115.0/24`) already exists in your file.

### 9.1 `.env`: additions

Your existing variables for the worker's identity on the network:

```dotenv
SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_HOSTNAME="pdf2chemicals_worker"
SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_HOSTNAME_IPV4="192.168.115.10"
```

> **Check line breaks.** In the text you sent, these two assignments appeared on a single line (`..._IPV4="192.168.115.10"SVC_..._HOSTNAME="pdf2chemicals_worker"`). In the real `.env` each assignment must be on its own line, otherwise the value is parsed incorrectly.

New variables needed by this guide (align the names with your existing naming convention):

```dotenv
# Service user (from `id svc_pdf2chemicals_prod` on the master)
SVC_PDF2CHEMICALS_PROD_USER=svc_pdf2chemicals_prod
SVC_PDF2CHEMICALS_PROD_UID=
SVC_PDF2CHEMICALS_PROD_GID=

# Torque server name (from /var/spool/torque/server_name on the master)
TORQUE_SERVER_HOST=feynman

# Address of the Docker host on the existing project network, where pbs_server is reachable.
# Usually the network gateway; confirm with:
#   docker network inspect <network> --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'
TORQUE_GATEWAY_IPV4=192.168.115.1

# Optional integrity check of the Torque tarball
TORQUE_SHA256=
```

### 9.2 Service: what to add or verify

Merge into the existing Celery worker service. Keep everything the service already defines (`command`, `env_file`, `depends_on`, volumes, ...).

```yaml
services:
  <your_celery_worker_service>:
    build:
      context: .
      args:
        SVC_USER: ${SVC_PDF2CHEMICALS_PROD_USER:-svc_pdf2chemicals_prod}
        SVC_UID: ${SVC_PDF2CHEMICALS_PROD_UID:?set SVC_PDF2CHEMICALS_PROD_UID in .env}
        SVC_GID: ${SVC_PDF2CHEMICALS_PROD_GID:?set SVC_PDF2CHEMICALS_PROD_GID in .env}
        TORQUE_SHA256: ${TORQUE_SHA256:-}
    # Already present in your file (verify): identity of the worker on the network
    hostname: ${SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_HOSTNAME}
    networks:
      <your_existing_network>:
        ipv4_address: ${SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_HOSTNAME_IPV4}
    # Add:
    init: true                                   # reaps zombies (trqauthd daemonizes)
    restart: unless-stopped
    stop_grace_period: 120s                      # let Celery finish its warm shutdown
    environment:
      TORQUE_SERVER_HOST: ${TORQUE_SERVER_HOST:?set TORQUE_SERVER_HOST in .env}
    extra_hosts:
      # TORQUE_SERVER_HOST must be the server HOSTNAME (as in its server_name file), not an IP.
      - "${TORQUE_SERVER_HOST}:${TORQUE_GATEWAY_IPV4}"
    healthcheck:
      # Checks that the Torque path works as the service user (queries the server)
      test: ["CMD-SHELL", "gosu $${SVC_USER} qstat -q > /dev/null"]
      interval: 60s
      timeout: 20s
      retries: 3
      start_period: 30s
```

Merge notes:

- **`environment`:** if your service already uses the list form (`- KEY=value`), add `- TORQUE_SERVER_HOST=...` in that form. Do not mix list and mapping forms in the same service.
- **`user:`:** remove it if present. The entrypoint starts as root to run `trqauthd` and then drops to the service user.
- **`entrypoint:`:** remove or chain it if your service already overrides it, because the image's entrypoint is what starts `trqauthd`.
- **`command:`:** keep it. It becomes the command run as the service user.
- **No `ports:`, no `network_mode: host`, no volumes for `/etc/passwd`, `/etc/group` or `/opt/torque`.**
- **Reserve the worker's IP.** Docker assigns addresses on the network dynamically to containers without a static one. Make sure `192.168.115.10` cannot be handed to another container (give your other services static addresses, or restrict the dynamic pool with `ipam` `ip_range` in the existing network definition).
- **Reachability.** The container must be able to reach TCP 15001 on `TORQUE_GATEWAY_IPV4`. If the existing network is declared `internal: true`, verify that traffic to the host address is still possible in your environment.
- **Broker.** The worker also needs to reach your Celery broker. Keep the broker settings your service already has. If it is attached to more than one network, check `ip route` inside the container to confirm that traffic to `TORQUE_GATEWAY_IPV4` leaves through the project network, so the server sees `192.168.115.10`.
- **Secrets.** Do not bake broker credentials into the image. Provide them through the environment, Docker secrets or your secret manager.

### 9.3 About the hostname `pdf2chemicals_worker`

The underscore matters for Torque. Standard host names (RFC 952/1123) contain letters, digits and hyphens, and an underscore is not valid in them. Local resolution through `/etc/hosts` often accepts it anyway, but DNS servers and some tools do not, and the Admin Guide asks for fully qualified names in `hosts.equiv`. Keep the name as you have it, but treat it as the **first suspect** if the trust check keeps failing after registration. In that case, switch to a standards-compliant name (for example `pdf2chemicals-worker`, or an FQDN) in `.env`, the server's `/etc/hosts` and `/etc/hosts.equiv` together.

---

## 10. Server-side registration

Run on the Torque server host (here, the master that also hosts the Docker daemon), as root, using the values from `.env`.

1. **Make the worker's name resolvable (both directions).** Add to `/etc/hosts`:

   ```
   192.168.115.10  pdf2chemicals_worker
   ```

   Verify:

   ```bash
   getent hosts pdf2chemicals_worker
   getent hosts 192.168.115.10
   ```

2. **Trust the host for submission.** Add the **bare hostname** to `/etc/hosts.equiv`:

   ```
   pdf2chemicals_worker
   ```

   This trusts the same-named user from that host, which is `svc_pdf2chemicals_prod`. Do not use the `host +` form.

3. **Alternative: `submit_hosts`.** The Admin Guide documents trusting submit hosts directly in the server configuration, without RCmd authentication:

   ```bash
   qmgr -c "set server submit_hosts += pdf2chemicals_worker"
   ```

   This was not tested in the prototype, and the guide warns that it is subject to DNS spoofing. Use it only in controlled and trusted environments, and only if you prefer it to `hosts.equiv`.

4. **Firewall.** In the prototype no firewall change was needed. If your host filters traffic from Docker networks, allow the project subnet to reach TCP 15001. Example for `firewalld`:

   ```bash
   firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.115.0/24" port port="15001" protocol="tcp" accept'
   firewall-cmd --reload
   ```

5. **Completed-job visibility** (needed by the `qstat`-based status check in section 11):

   ```bash
   qmgr -c "set server keep_completed = 86400"
   ```

   Choose a value longer than the longest interval between two status polls of the same job.

---

## 11. Application changes

### Submit directly, without the shell wrapper

The worker already runs as `svc_pdf2chemicals_prod`, so call the Torque clients directly. Remove `TORQUE_USER_HOME`, the `sh -c "(cd ... && ...)"` wrapper and `shell=True`.

```python
import subprocess
from celery import shared_task

@shared_task
def submit_job(script_path: str) -> str:
    result = subprocess.run(
        ["qsub", script_path],        # add flags as needed (-N, -l, -d, ...)
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return result.stdout.strip()      # job ID, for example "57259.feynman"
```

### Replace `tracejob` with `qstat -f`

`tracejob` reads the server's log files from disk, which a client container does not have. The job state and exit status are available through `qstat -f`:

| Need | `qstat -f` attribute |
|---|---|
| Job state (`Q`, `R`, `E`, `C`, ...) | `job_state` |
| Exit code | `exit_status` (may be negative for jobs that failed to start) |
| Resources used | `resources_used.*` |

Use the `pbs_job_status.py` module delivered with this work (`get_pbs_job_status`, `is_pbs_job_completed`). It has no shell, no `grep` and no `tracejob`. Behavior to keep in mind:

- It requires `keep_completed` (section 10, step 5). After the server purges a job, `qstat` returns `Unknown Job Id`. The module reports `COMPLETED` in that case, like the previous implementation, but cannot tell success from failure. Persist the terminal status in your application the first time you see it.
- Connection or authentication errors return `UNKNOWN` instead of being treated as a finished job.
- If you submit job arrays (`qsub -t`), each sub-job needs its own query. Review that logic before using it with arrays.

---

## 12. Build, run and validate

```bash
docker compose build <your_celery_worker_service>
docker compose up -d <your_celery_worker_service>
docker compose ps
docker compose logs <your_celery_worker_service>
```

Validate Torque from inside the container as the service user:

```bash
docker compose exec -u svc_pdf2chemicals_prod <your_celery_worker_service> bash -c '
  id
  qstat --version
  qstat -q
  echo "sleep 30" | qsub
  qstat'
```

Checklist:

- [ ] The image builds from the local tarball and the `ldd` guard passes.
- [ ] `id` shows the service user with group `torque_queue_batch`.
- [ ] `qstat --version` matches the server (6.1.3).
- [ ] `qsub` returns a job ID ending with the server name (`<id>.feynman`).
- [ ] `qstat -f <job_id>` shows `euser = svc_pdf2chemicals_prod` and, after completion, `job_state = C` and `exit_status`.
- [ ] The Celery worker connects to the broker and runs a test task that submits a job.
- [ ] The container is `healthy` in `docker compose ps`.
- [ ] No mounts of `/etc/passwd`, `/etc/group` or `/opt/torque` remain in any Compose file.

---

## 13. Operations notes

- **Scaling.** The worker has a fixed hostname and IP registered on the server. Extra replicas would not be trusted, and a static IP cannot be shared (`docker compose up --scale` conflicts on it). Prefer raising Celery's `--concurrency` within the single container (a single `trqauthd` handles concurrent clients). If you need several containers, define separate services, each with its own hostname and IP, and register each one on the server (section 10).
- **Changing hostname or IP.** Update `.env`, the server's `/etc/hosts` and `/etc/hosts.equiv` together.
- **Torque version upgrades.** Replace the tarball in `vendor/`, update `TORQUE_SHA256` and rebuild. Keep client and server versions aligned.
- **Base image updates.** Rebuild periodically to receive Debian and Python security updates, re-run the validation checklist, and plan the move from bookworm (security support by the Debian LTS team until mid-2028) to a newer release.
- **Healthcheck.** The provided check queries the server every minute as the service user. Adjust the interval to your load, and add a Celery-level check (for example `celery inspect ping`) if you want the health status to reflect the worker as well.

---

## 14. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `Bad UID for job execution MSG=ruserok failed validating <user>/<user> from <host>` | The server does not trust `<host>` | Check `/etc/hosts` and `/etc/hosts.equiv` on the server. Trust the exact name printed after `from`. If the name contains an underscore or is not fully qualified, see section 9.3 |
| `Unauthorized Request` | Queue ACL or host restrictions | `qmgr -c "p q batch"` and `qmgr -c "p s"`; check `acl_hosts`, `acl_host_enable` and group ACLs |
| Container exits right after start | `trqauthd` failed, wrong `server_name`, CRLF in the entrypoint, or a missing `.env` variable | `docker compose logs <service>`; check name resolution of `TORQUE_SERVER_HOST` |
| `Could not open socket in trq_simple_connect. error 97` | The Admin Guide associates this with duplicate `/etc/hosts` entries for one name | Check `/etc/hosts` inside the container for duplicates of the same name |
| Cannot connect to the server | `extra_hosts` mapping wrong, server not listening on the gateway interface, firewall | Verify `getent hosts $TORQUE_SERVER_HOST` in the container and the firewall rule for TCP 15001 |
| `qsub` works but the job never starts or runs as the wrong user | User or UID/GID mismatch on the execution node | `id svc_pdf2chemicals_prod` on the master and on a MOM must match the image |
| Build fails in `configure` or `make` | Toolchain/dependency issue with the 2018-era source on the new base image | Read the first error; add the missing `-dev` package to the build stage and the runtime library to the final stage; see the fallbacks in section 5 |
| Build guard reports `not found` libraries | Runtime library missing in the final stage | Add the package that provides it to the `apt-get install` of stage 2 |
| Celery cannot reach the broker | Network placement or routing | Check networks and `ip route` in the container |
| Values from `.env` look wrong or empty | Two assignments on one line, or missing quotes | Make sure each variable is on its own line |
| `qstat` reports `Unknown Job Id` for a finished job | Job purged after `keep_completed` | Increase `keep_completed` and persist final status in the application |

Server-side debugging while reproducing the problem:

```bash
tail -f /var/spool/torque/server_logs/$(date +%Y%m%d)
```

---

## 15. Summary of what is decoupled from the host

| Before | After |
|---|---|
| Host `/etc/passwd` and `/etc/group` mounted into containers | Service user and group created in the image (same name, UID, GID as NIS) |
| Personal account used through `sh -c "(cd ... && qsub ...)"` | Celery runs as `svc_pdf2chemicals_prod` and calls `qsub` directly |
| Torque binaries tied to the host | Torque 6.1.3 clients built into the image from the same tarball as the server |
| `tracejob` reading server log files | `qstat -f` over the network |
| Unstable source identity on the default bridge | The worker's fixed hostname and IP on the project network, registered on the server |
| No published ports | Still none: the container only connects outbound to the server |

Remember: this is a guideline. Review each section against your environment, validate the Debian build in a non-production setting first, and adapt the security choices to your organization's requirements.
