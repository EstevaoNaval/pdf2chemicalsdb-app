import logging
from io import BytesIO

import requests
from django.conf import settings

from celery import shared_task

logger = logging.getLogger(__name__)

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

    r = requests.patch(
        url=settings.API_BASE_URL+f"/api/chemicals/admin/{chemical_id}/",
        files=files,
        headers={
            'Authorization': 'Bearer {}'.format(settings.CELERY_AUTH_TOKEN)
        }
    )
    
    r.raise_for_status()

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
    
    r = requests.patch(
        url=settings.API_BASE_URL+f"/api/chemicals/admin/{chemical_id}/",
        files=files,
        headers={
            'Authorization': 'Bearer {}'.format(settings.CELERY_AUTH_TOKEN)
        }
    )
    
    r.raise_for_status()

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
    
    r = requests.post(
        url=settings.API_BASE_URL+"/api/chemicals/admin/",
        json=chemical,
        headers={
            'Authorization': 'Bearer {}'.format(settings.CELERY_AUTH_TOKEN)
        }
    )
    
    r.raise_for_status()
    
    chemical_id = r.json().get("api_id")
    
    patch_conformation.apply_async(args=[chemical_id, conformations], priority=10)
    patch_depiction.apply_async(args=[chemical_id, chem_depiction_image], priority=10)