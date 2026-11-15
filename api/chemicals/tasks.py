import logging
import os
from io import BytesIO

import requests
from django.conf import settings

from celery import shared_task

logger = logging.getLogger(__name__)


class _WorkerApi:
    """Knox session for django-worker chemical writes.

    `_worker_api` is the one instance. post_chemical, patch_conformation, and
    patch_depiction call it. It holds the current token and reuses it until a
    401, then logs in once more. Input: a requests method, an absolute URL, and
    that method's body kwargs. Output: the response after raise_for_status.
    """

    def __init__(self):
        self.token = None

    def __call__(self, method, url, **kwargs):
        email = os.environ.get("DJANGO_WORKER_API_EMAIL")
        password = os.environ.get("DJANGO_WORKER_API_PASSWORD")
        if not email or not password:
            raise RuntimeError(
                "DJANGO_WORKER_API_EMAIL and DJANGO_WORKER_API_PASSWORD must be set"
            )

        for attempt in (1, 2):
            if self.token is None:
                login = requests.post(
                    f"{settings.API_BASE_URL}/api/auth/login/",
                    json={"username": email, "password": password},
                )
                login.raise_for_status()
                self.token = login.json()["token"]

            response = method(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                **kwargs,
            )
            if response.status_code != 401:
                response.raise_for_status()
                return response

            self.token = None
            if attempt == 2:
                response.raise_for_status()

        return response


_worker_api = _WorkerApi()

# One MIME per text format written into JSON ``conformation``.
_CONF_MIME = {
    "pdb": "chemical/x-pdb",
    "sdf": "chemical/x-mdl-sdfile",
    "mol2": "chemical/x-mol2",
    "smi": "chemical/x-daylight-smiles",
}


@shared_task(
    name='chemicals.tasks.django_tasks_patch_conformation', 
    bind=True,
    queue='django_tasks',
    priority=10,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 5, 'countdown': 60},
    retry_backoff=True,
    task_reject_on_worker_lost=True
)
def patch_conformation(self, chemical_id: str, conformations: dict[str, list[str]]):
    if not isinstance(conformations, dict):
        logger.warning(
            "Skipping conformations for %s: expected a format object, got %s",
            chemical_id,
            type(conformations).__name__,
        )
        return

    files = {}
    number = 0
    for fmt, texts in conformations.items():
        if fmt not in _CONF_MIME:
            continue
        if not isinstance(texts, list):
            continue
        for text in texts:
            files[f"conformations[{number}][conf_file]"] = (
                f"conf_{number}.{fmt}",
                BytesIO(text.encode("utf-8")),
                _CONF_MIME[fmt],
            )
            number += 1

    if not files:
        return

    _worker_api(
        requests.patch,
        f"{settings.API_BASE_URL}/api/chemicals/{chemical_id}/",
        files=files,
    )

@shared_task(
    name='chemicals.tasks.django_tasks_patch_depiction', 
    bind=True, 
    queue='django_tasks',
    priority=10,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 5, 'countdown': 60},
    retry_backoff=True,
    task_reject_on_worker_lost=True
)
def patch_depiction(self, chemical_id, depiction: str):
    files = {}
    
    files['depiction_image'] = (
        'depiction_image.svg',
        BytesIO(depiction.encode('utf-8')),
        "image/svg+xml"
    )
    
    _worker_api(
        requests.patch,
        f"{settings.API_BASE_URL}/api/chemicals/{chemical_id}/",
        files=files,
    )

@shared_task(
    name='chemicals.tasks.django_tasks_post_chemical', 
    bind=True, 
    queue='django_tasks',
    priority=10,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 5, 'countdown': 60},
    retry_backoff=True,
    task_reject_on_worker_lost=True
)
def post_chemical(self, chemical: dict, user_id: int):
    conformations = chemical.pop('conformation', [])
    chem_depiction_image = chemical.pop('chem_depiction_image', '')
    
    chemical['user'] = user_id    
    
    r = _worker_api(
        requests.post,
        f"{settings.API_BASE_URL}/api/chemicals/",
        json=chemical,
    )
    
    chemical_id = r.json().get("api_id")
    
    patch_conformation.apply_async(args=[chemical_id, conformations], priority=10)
    patch_depiction.apply_async(args=[chemical_id, chem_depiction_image], priority=10)