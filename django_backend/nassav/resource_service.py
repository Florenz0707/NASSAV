"""Production resource facade, kept for HTTP, jobs and synchronous consumers."""

from nassav.composition import build_resource_service
from nassav.resource_workflow import (
    ResourceAccessDeniedError as ResourceAccessDeniedError,
)
from nassav.resource_workflow import (
    ResourceAlreadyExistsError as ResourceAlreadyExistsError,
)
from nassav.resource_workflow import (
    ResourceFetchError as ResourceFetchError,
)
from nassav.resource_workflow import (
    ResourceNotFoundError as ResourceNotFoundError,
)
from nassav.resource_workflow import (
    ResourceService as ResourceService,
)
from nassav.resource_workflow import (
    ResourceServiceException as ResourceServiceException,
)

resource_service = build_resource_service()
