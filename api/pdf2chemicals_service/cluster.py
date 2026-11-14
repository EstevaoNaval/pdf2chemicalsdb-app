"""PBS script helpers and the Torque gateway client for the pdf2chemicals worker.

Tasks call these functions. Submit, status, and delete are HTTP calls to
torque-gateway. Inputs are script fields and job ids. Outputs are script paths
under MEDIA_ROOT, job ids, and status strings: COMPLETED, FAILED, RUNNING,
QUEUED, UNKNOWN.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

from django.conf import settings

from .util.util import generate_random_alphanumeric_sequence


def replace_job_id_in_template(script_content: str):
    JOB_ID_SIZE = 10
    job_id = generate_random_alphanumeric_sequence(JOB_ID_SIZE)

    script_content = script_content.replace("{{job_id}}", job_id)

    return script_content


def replace_java_home_in_template(script_content: str):
    script_content = script_content.replace("{{JAVA_HOME}}", os.getenv("JAVA_HOME"))
    return script_content


def replace_conda_env_in_template(script_content: str):
    script_content = script_content.replace("{{conda_env}}", os.getenv("CONDA_ENV"))
    return script_content


def replace_pdf2chemicals_path_in_template(script_content: str):
    pdf2chemicals_path = get_pdf2chemicals_path()

    script_content = script_content.replace(
        "{{pdf2chemicals_path}}", pdf2chemicals_path
    )
    return script_content


def replace_pdf_path_in_template(script_content: str, pdf_path: str):
    script_content = script_content.replace("{{pdf_path}}", pdf_path)
    return script_content


def replace_output_dir_in_template(script_content: str, output_dir: str):
    script_content = script_content.replace("{{output_dir}}", output_dir)
    return script_content


def replace_export_format_in_template(script_content: str, export_format: str):
    export_format_content = "--format json "

    if export_format == "zip":
        export_format_content += f"--format {export_format} "

    script_content = script_content.replace("{{export_format}}", export_format_content)

    return script_content


def replace_conf_formats_in_template(script_content: str, conf_formats: list[str]):
    conf_formats_content = ""

    for fmt in conf_formats:
        conf_formats_content += f"-conf-fmt {fmt} "

    script_content = script_content.replace("{{conf_formats}}", conf_formats_content)

    return script_content


def replace_structure_formats_in_template(
    script_content: str, structure_formats: list[str]
):
    structure_formats_content = ""

    for fmt in structure_formats:
        structure_formats_content += f"-structure-fmt {fmt} "

    script_content = script_content.replace(
        "{{structure_formats}}", structure_formats_content
    )

    return script_content


def replace_filename_formats_in_template(script_content: str, filename: str):
    script_content = script_content.replace("{{filename}}", f"--filename {filename}")
    return script_content


# Function to generate a script name with a random suffix
def generate_script_name(base_name="pbs-script") -> str:
    """
    Generates a unique PBS script name with a uuid4 suffix.\n
    Returns: The script name with the random suffix.
    """

    return f"{base_name}-{uuid.uuid4()}.pbs"


# Function to save the generated script in the media directory
def save_script(script_content):
    """
    Saves the PBS script content to a file inside MEDIA_ROOT.

    Parameters:
    - script_content: The content of the PBS script.
    - script_name: The name of the file where the script will be saved.
    """
    # Directory to save PBS scripts
    pbs_scripts_dir = os.path.join(settings.MEDIA_ROOT, "pbs_scripts")

    # Generate the script name with a random suffix
    script_name = generate_script_name()

    # Ensure the directory exists, otherwise create it
    os.makedirs(pbs_scripts_dir, exist_ok=True)

    # Full path to the file where the script will be saved
    script_path = os.path.join(pbs_scripts_dir, script_name)

    # Save the script to the file
    with open(script_path, "w") as file:
        file.write(script_content)

    return script_path


def get_pdf2chemicals_pbs_template_path():
    return os.path.join(
        os.path.dirname(__file__), "pbs_template", "pdf2chemicals_pbs_template.pbs"
    )


def get_pdf2chemicals_path():
    return os.path.join(
        settings.BASE_ROOT_DIR, "libs", "pdf2chemicals", "pdf2chemicals.py"
    )


def get_pbs_script_content():
    template_path = get_pdf2chemicals_pbs_template_path()

    # Load the template content
    with open(template_path, "r") as file:
        script_content = file.read()

    return script_content


def generate_pbs_script(
    pdf_path,
    output_dir,
    export_format,
    conf_formats,
    structure_formats,
    filename,
):
    """
    Generates a PBS script for chemical processing by replacing the necessary variables.

    Parameters:
    - pdf_path: Path to the PDF to be processed.
    - output_dir: Directory where the results will be saved.
    - filename: Prefix for the output JSON file.
    """
    script_content = get_pbs_script_content()

    script_content = replace_job_id_in_template(script_content)
    # #PBS -d sets PBS_O_WORKDIR. The MOM must already have this path.
    script_content = script_content.replace(
        "{{torque_user_home}}", os.environ["TORQUE_USER_HOME"]
    )
    script_content = replace_java_home_in_template(script_content)
    script_content = replace_conda_env_in_template(script_content)
    script_content = replace_pdf2chemicals_path_in_template(script_content)
    script_content = replace_pdf_path_in_template(script_content, pdf_path)
    script_content = replace_output_dir_in_template(script_content, output_dir)
    script_content = replace_export_format_in_template(script_content, export_format)
    script_content = replace_conf_formats_in_template(script_content, conf_formats)
    script_content = replace_structure_formats_in_template(
        script_content, structure_formats
    )
    script_content = replace_filename_formats_in_template(script_content, filename)

    # Save the generated script in the media directory
    script_path = save_script(script_content)

    return script_path


_GATEWAY_TIMEOUT_SECONDS = 60
_JOB_STATUSES = ("COMPLETED", "FAILED", "RUNNING", "QUEUED", "UNKNOWN")


def _gateway_token() -> str:
    token = os.environ.get("TORQUE_GATEWAY_TOKEN", "").strip()
    if token:
        return token
    token_file = os.environ.get("TORQUE_GATEWAY_TOKEN_FILE", "")
    if not token_file:
        raise RuntimeError("TORQUE_GATEWAY_TOKEN or TORQUE_GATEWAY_TOKEN_FILE must be set")
    with open(token_file) as fh:
        token = fh.read().strip()
    if not token:
        raise RuntimeError("Torque gateway token file is empty")
    return token


def _gateway_call(method: str, path: str, body: dict | None = None):
    """Call the gateway. Returns (HTTP status or None, JSON object).

    None means the gateway was not reached. Callers must not treat that as a
    finished job.
    """
    base = os.environ.get("TORQUE_GATEWAY_URL", "").rstrip("/")
    if not base:
        return None, {}

    data = None
    headers = {"Authorization": "Bearer " + _gateway_token()}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        base + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=_GATEWAY_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                return response.status, {}
            return response.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return exc.code, payload
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None, {}


def _job_path(job_id: str) -> str:
    return "/jobs/" + urllib.parse.quote(job_id, safe="")


def submit_pbs_script(script_text: str) -> str:
    """POST the rendered script. PBS directives are inside the file, not qsub flags."""
    if not script_text or not script_text.strip():
        raise ValueError("PBS script is empty")

    status, payload = _gateway_call("POST", "/jobs", {"script": script_text})
    job_id = payload.get("job_id")
    if status != 201 or not job_id:
        detail = payload.get("detail") or payload.get("error") or "gateway submit failed"
        raise RuntimeError(str(detail))
    return str(job_id)


def delete_hpc_job(job_id: str):
    if not job_id or job_id.startswith("-"):
        return
    _gateway_call("DELETE", _job_path(job_id))


def get_pbs_job_status(job_id: str) -> str:
    """Status from the gateway: COMPLETED, FAILED, RUNNING, QUEUED, or UNKNOWN.

    A 404 NOT_FOUND is COMPLETED. That is the previous Unknown Job Id fallback:
    the server has purged the job after keep_completed. A connection error stays
    UNKNOWN so the monitor retries.
    """
    if not job_id or job_id.startswith("-"):
        return "UNKNOWN"

    status, payload = _gateway_call("GET", _job_path(job_id))
    if status is None:
        return "UNKNOWN"
    # Purged after keep_completed. Same fallback as the old "Unknown Job Id" path.
    if status == 404 and payload.get("status") == "NOT_FOUND":
        return "COMPLETED"
    if status != 200:
        return "UNKNOWN"

    job_status = payload.get("status")
    if job_status in _JOB_STATUSES:
        return job_status
    return "UNKNOWN"


def is_pbs_job_completed(job_id: str) -> bool:
    """True when the job has finished, successfully or not."""
    return get_pbs_job_status(job_id) in ("COMPLETED", "FAILED")
