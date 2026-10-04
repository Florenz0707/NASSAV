"""Production resource facade, kept for HTTP, jobs and synchronous consumers."""

from nassav.resource_workflow import (
    ResourceServiceException as ResourceServiceException,
    ResourceAlreadyExistsError as ResourceAlreadyExistsError,
    ResourceNotFoundError as ResourceNotFoundError,
    ResourceAccessDeniedError as ResourceAccessDeniedError,
    ResourceFetchError as ResourceFetchError,
    ResourceService as ResourceService,
)
from nassav.composition import build_resource_service

resource_service = build_resource_service()
