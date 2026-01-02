from rest_framework import status
from rest_framework.response import Response

STATUS_MAP = {
    200: status.HTTP_200_OK,
    201: status.HTTP_201_CREATED,
    202: status.HTTP_202_ACCEPTED,
    400: status.HTTP_400_BAD_REQUEST,
    404: status.HTTP_404_NOT_FOUND,
    409: status.HTTP_409_CONFLICT,
    500: status.HTTP_500_INTERNAL_SERVER_ERROR,
    502: status.HTTP_502_BAD_GATEWAY,
}


def build_response(code: int, message: str, data=None, pagination: dict = None):
    """Return a DRF Response using project's envelope and mapped HTTP status.

    All views should call this helper to produce consistent responses. Optionally
    include a `pagination` dict when returning paged list results.
    """
    http_status = STATUS_MAP.get(code, status.HTTP_200_OK)
    body = {"code": code, "message": message, "data": data}
    if pagination is not None:
        body["pagination"] = pagination
    return Response(body, status=http_status)
