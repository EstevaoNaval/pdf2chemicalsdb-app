# Stage 1: Build stage
FROM python:3.12-slim AS builder

# Definir o diretório de trabalho no container
WORKDIR /src

# Set environment variables to optimize Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Atualizar pip e instalar as dependências do Django
RUN pip install --upgrade pip
COPY requirements.txt /src/
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Production stage
FROM python:3.12-slim

ARG USER
ARG UID
ARG GID
# Set only by the pdf2chemicals worker. Django images leave these empty.
ARG DATA_GROUP=""
ARG DATA_GID=""

# Instalar dependências do sistema (caso necessário)
RUN apt-get update && \
apt-get install -y gosu && \
rm -rf /var/lib/apt/lists/*

# Primary group is GID. DATA_GID is a second group for the shared data directory,
# and only when it is a different number (two groupadds with one GID fail).
RUN addgroup --gid ${GID} ${USER} \
 && adduser --disabled-password --no-create-home --uid ${UID} --gid ${GID} --shell /bin/sh ${USER} \
 && if [ -n "${DATA_GID}" ] && [ "${DATA_GID}" != "${GID}" ]; then \
      addgroup --gid ${DATA_GID} ${DATA_GROUP} \
      && adduser ${USER} ${DATA_GROUP}; \
    fi \
 && mkdir /src \
 && chown -R ${USER} /src

# Definir o diretório de trabalho
WORKDIR /src

# Copiar as dependências Python da primeira etapa (builder)
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copiar código da aplicação
COPY --chown=${USER}:${USER} . .

# Set environment variables to optimize Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Definir o script de entrada
ENTRYPOINT ["/bin/sh", "-c", "chmod +x ${ENTRYPOINT_PATH} && exec ${ENTRYPOINT_PATH}"]
