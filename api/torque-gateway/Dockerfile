# =============================================================================
# Torque gateway -- CentOS 7 + Torque 6.1.3 clients + HTTP gateway (gateway.py)
#
# Build context is api/ (the directory that contains vendor/ and torque-gateway/).
# Same Torque flow as the validated prototype: configure, make, make packages,
# clients package --install, trqauthd as root, privilege drop with gosu.
# No Python build: the gateway uses the Python 3.6 shipped by CentOS 7.
#
# Build:
#   docker build \
#     --build-arg SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_UID=<uid> \
#     --build-arg SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_GID=<primary gid> \
#     --build-arg TORQUE_QUEUE_GID=<gid of torque_queue_batch> \
#     -f torque-gateway/Dockerfile \
#     -t pdf2chemicals-torque-gateway .
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

# Identity must match the cluster (NIS): same names, UIDs and GIDs.
# The two GIDs must differ. groupadd fails if they are the same number.
ARG SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_USER=svc_pdf2chemicals_prod
ARG SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_UID
ARG SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_GID
ARG TORQUE_QUEUE_GID
ARG GOSU_VERSION=1.17
ARG GOSU_SHA256=""

ENV SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_USER=${SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_USER} \
    GATEWAY_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:/usr/local/sbin:${PATH}"

RUN sed -i -e 's|^mirrorlist=|#mirrorlist=|g' \
           -e 's|^#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' \
           /etc/yum.repos.d/CentOS-*.repo

# Runtime libraries for the Torque clients, system Python 3.6, and curl
# (gosu download below, and the Compose healthcheck).
RUN yum install -y openssl-libs libxml2 python3 curl \
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
RUN groupadd -g ${SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_GID} ${SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_USER} \
 && groupadd -g ${TORQUE_QUEUE_GID} torque_queue_batch \
 && useradd -m -u ${SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_UID} -g ${SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_GID} -G torque_queue_batch \
      -s /sbin/nologin ${SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_USER}

# Gateway (root-owned, read-only for the service user)
COPY torque-gateway/gateway.py /opt/gateway/gateway.py
RUN python3 -c "import ast; ast.parse(open('/opt/gateway/gateway.py').read())"

COPY torque-gateway/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
 && chmod +x /usr/local/bin/docker-entrypoint.sh

# Documentation only: nothing is published to the host. Reachable on the project network only.
EXPOSE 8080

# Do NOT set USER here: the entrypoint needs root to start trqauthd, then drops to the service user
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python3", "/opt/gateway/gateway.py"]
