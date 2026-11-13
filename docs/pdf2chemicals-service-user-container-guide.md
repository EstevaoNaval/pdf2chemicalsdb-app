# Decoupling Docker Compose Containers from the Host for PBS Torque Submission

> Superseded for this repo by [torque-celery-production-guide.md](torque-celery-production-guide.md). Follow that guide and its "This repo" section. This file is the shorter earlier draft.

## 1. Goal

Submit jobs (`qsub`, `qstat`, `qdel`, ...) from containers using a dedicated **service user** (`svc_pdf2chemicals_prod`), removing two workarounds currently in place:

| Workaround to remove                                                  | Why it was needed                                                                                                        | Replacement                                                                                       |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| Mounting the host's `/etc/passwd` and `/etc/group` into the container | The Torque client resolves the current UID to a user name via `getpwuid()`. Without a matching entry, the request fails. | Create the user and group **inside the image** with the same name, UID and GID as in the cluster. |
| `sh -c "(cd $TORQUE_USER_HOME && qsub ...)"` using a personal account | The service user was rejected by the server.                                                                             | Run the application as `svc_pdf2chemicals_prod` directly.                                         |

## 2. Prerequisites (already done on the cluster side)

- `svc_pdf2chemicals_prod` exists on the master (`pbs_server`) and on every MOM node, published through NIS.
- `svc_pdf2chemicals_prod` belongs to the group `torque_queue_batch`.
- NIS maps were rebuilt (`make -C /var/yp`) and the user resolves via `getent passwd svc_pdf2chemicals_prod` on all nodes.

## 3. Step 1: Collect the identity values from the master

Run on the master:

```bash
id svc_pdf2chemicals_prod
getent passwd svc_pdf2chemicals_prod
getent group torque_queue_batch
```

Record these values. The container must match them exactly:

| Value              | Example                  | Used in                |
| ------------------ | ------------------------ | ---------------------- |
| User name          | `svc_pdf2chemicals_prod` | Dockerfile, entrypoint |
| UID                | `1500`                   | `SVC_UID` build arg    |
| Primary GID        | `<GID>`                  | `SVC_GID` build arg    |
| Group name         | `torque_queue_batch`     | Dockerfile             |
| Torque server name | `<master_hostname>`      | `TORQUE_SERVER_HOST`   |

> **Note:** `molmod-cs.uff.br` seen in `/var/yp` is the **NIS domain**, not necessarily the Torque server hostname. Use the content of `/var/spool/torque/server_name` from a working client (or the master's hostname) for `TORQUE_SERVER_HOST`.

## 4. Step 2: Update the Dockerfile

Create the group and user in the image, and make sure `gosu` is available to drop privileges.

```dockerfile
# ... base image and Torque client installation (unchanged) ...

ARG SVC_UID=1500
ARG SVC_GID=<GID>

# gosu: drop privileges from root to svc_pdf2chemicals_prod in the entrypoint
RUN apt-get update \
 && apt-get install -y --no-install-recommends gosu \
 && rm -rf /var/lib/apt/lists/*

# Same name/UID/GID as the cluster (NIS)
RUN groupadd -g ${SVC_GID} torque_queue_batch \
 && useradd -m -u ${SVC_UID} -g torque_queue_batch -s /bin/bash svc_pdf2chemicals_prod

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["<your application command>"]
```

Notes:

- If the base image already has a group or user using that GID/UID, `groupadd`/`useradd` will fail. Remove or change the conflicting entry, or pick a base image without it.
- If on the master `torque_queue_batch` is a **secondary** group of `svc_pdf2chemicals_prod` (created with `-G`), mirror that: create a separate primary group and add the user with `-G torque_queue_batch`.
- Do **not** set `USER svc_pdf2chemicals_prod` in the Dockerfile. The entrypoint needs root first to start `trqauthd`.
- Use `su-exec` or `setpriv` if you prefer to avoid `gosu` (and adjust the package manager if the image is not Debian/Ubuntu-based).

## 5. Step 3: Create the entrypoint script

`docker-entrypoint.sh`:

```bash
#!/bin/sh
set -e

# Point the Torque client to the master
# (verify the spool path for your Torque package: /var/spool/torque or /var/lib/torque)
echo "${TORQUE_SERVER_HOST}" > /var/spool/torque/server_name

# trqauthd must start as root
trqauthd

# Drop privileges and run the application as the service user
exec gosu svc_pdf2chemicals_prod "$@"
```

Why this order matters:

1. `trqauthd` is the authorization daemon used by every Torque client command. It requires root to run.
2. After it is up, the application (and every `qsub` it spawns) runs as `svc_pdf2chemicals_prod`, so the UID resolves to the name the server expects.
3. `exec` makes the application PID 1 (proper signal handling by Docker).

## 6. Step 4: Update `docker-compose.yml`

```yaml
services:
  worker:
    build:
      context: .
      args:
        SVC_UID: 1500
        SVC_GID: <GID>
    hostname: worker-torque # fixed hostname, easier to authorize on the server
    environment:
      TORQUE_SERVER_HOST: <master_hostname>
    # REMOVE these (no longer needed):
    # volumes:
    #   - /etc/passwd:/etc/passwd:ro
    #   - /etc/group:/etc/group:ro
    # environment:
    #   TORQUE_USER_HOME: ...
    # DO NOT set `user:`; the entrypoint handles privilege drop.
```

If the container cannot resolve the master hostname through DNS, add:

```yaml
extra_hosts:
  - "<master_hostname>:<master_ip>"
```

## 7. Step 5: Update the application code

Remove the `sh -c "(cd ... && qsub ...)"` wrapper and call `qsub` directly. The process already runs as `svc_pdf2chemicals_prod`.

**Before:**

```python
cmd = f'sh -c "(cd {os.getenv("TORQUE_USER_HOME")} && {qsub_cmd})"'
subprocess.run(cmd, shell=True, check=True)
```

**After:**

```python
import subprocess

result = subprocess.run(
    ["qsub", script_path],        # add flags as needed: "-o", out_path, "-e", err_path, "-d", workdir
    capture_output=True,
    text=True,
    check=True,
)
job_id = result.stdout.strip()
```

Cleanup checklist:

- [ ] Delete every use of `TORQUE_USER_HOME`.
- [ ] Remove the `sh -c "(cd ... )"` wrapper and `shell=True` (pass arguments as a list).
- [ ] Remove `TORQUE_USER_HOME` from `.env`, compose files and documentation.
- [ ] Confirm that job script paths and `-o`/`-e`/`-d` targets are valid **on the MOM nodes** (shared filesystem, or paths that exist there), since the job runs there as `svc_pdf2chemicals_prod`.

## 8. Step 6: Build and validate

```bash
docker compose build --no-cache worker
docker compose up -d worker
docker compose exec worker bash
```

Inside the container, run:

```bash
id                           # expect: svc_pdf2chemicals_prod with torque_queue_batch
getent passwd svc_pdf2chemicals_prod     # resolves locally (from the image)
pgrep trqauthd               # daemon is running
cat /var/spool/torque/server_name

echo 'echo ok; hostname' | qsub
qstat
```

Then verify the job output on the cluster side (default output files are written to the user's home on the execution node, unless `-o`/`-e`/`-d` were set).

Validation checklist:

- [ ] Container starts **without** the host `passwd`/`group` mounts.
- [ ] `qsub` succeeds as `svc_pdf2chemicals_prod`.
- [ ] `qstat` lists the job and the owner is `svc_pdf2chemicals_prod`.
- [ ] `qdel <job_id>` works for jobs submitted by the same user.
- [ ] Job output/error files are created in the expected location.

## 9. Troubleshooting

| Symptom                                   | Likely cause                                                                        | Action                                                                                                                                                              |
| ----------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Unauthorized Request`                    | Submit host not allowed, or queue ACL                                               | On the master: `qmgr -c "p s" \| grep -E "submit_hosts\|allow_node_submit"` and `qmgr -c "p q batch" \| grep acl`. Add the Docker host to `submit_hosts` if needed. |
| `Bad UID for job execution`               | Name/UID mismatch between container and cluster, or user not resolved by the server | Compare `id` in the container against `id svc_pdf2chemicals_prod` on the master.                                                                                    |
| Cannot connect / authentication error     | `trqauthd` not running, wrong `server_name`, port 15001 unreachable                 | Check `pgrep trqauthd`, `cat /var/spool/torque/server_name`, and network access to the master.                                                                      |
| `trqauthd` fails to start                 | Container is running as non-root from the start                                     | Remove `user:` from compose and `USER` from the Dockerfile; let the entrypoint drop privileges.                                                                     |
| Job runs but output is missing/unwritable | Home or workdir does not exist on the MOM, or UID/GID mismatch on shared storage    | Ensure `/home/svc_pdf2chemicals_prod` (or chosen paths) exist on the MOMs, or use `-o`/`-e`/`-d`.                                                                   |
| `groupadd`/`useradd` fails during build   | UID/GID already used in the base image                                              | Free the conflicting entry or adjust the base image.                                                                                                                |

Server-side debugging, while submitting from the container:

```bash
tail -f /var/spool/torque/server_logs/$(date +%Y%m%d)
```

The log line identifies whether the rejection is about the user, group, submit host, or ACL.

## 10. Final state

- Containers are self-contained: identity is baked into the image, not borrowed from the host.
- The application submits jobs as the dedicated `svc_pdf2chemicals_prod` account, without personal credentials.
- No host files mounted for user resolution and no shell wrapper changing directories to a personal home.
