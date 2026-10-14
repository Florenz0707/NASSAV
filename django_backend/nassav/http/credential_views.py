"""Blind credential writes; admission remains operator-only until multi-user P8."""

from rest_framework.permissions import BasePermission

from nassav.access import is_operator
from nassav.api_utils import build_response
from nassav.composition import build_credential_records
from nassav.credential_crypto import CredentialUnavailable
from nassav.credential_models import SourceCredential
from nassav.http.account_views import IsAdminOperator
from nassav.http_base import SchemaAPIView
from nassav.credential_records import public_credential
from nassav.source_credentials import CredentialConflict


class CredentialAdmission(BasePermission):
    def has_permission(self, request, view):
        return is_operator(request.user)


class SourceCredentialsView(SchemaAPIView):
    permission_classes = [CredentialAdmission]
    credential_scope = "personal"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def rows(self, request):
        return SourceCredential.objects.filter(
            scope=self.credential_scope,
            owner_id=request.user.pk if self.credential_scope == "personal" else None,
        )

    def get(self, request):
        return build_response(
            200,
            "success",
            [
                public_credential(row)
                for row in self.rows(request).order_by("source_name")
            ],
        )

    def post(self, request):
        return self.execute(request)

    def execute(self, request, credential_id=None, *, revoke=False):
        if not isinstance(request.data, dict):
            return build_response(400, "请求必须为对象", None)
        payload = dict(request.data)
        if credential_id is None:
            source_name = payload.pop("source_name", None)
            if not isinstance(source_name, str):
                return build_response(400, "需要source_name", None)
        else:
            row = self.rows(request).filter(pk=credential_id).first()
            if row is None:
                return build_response(404, "凭证不存在", None)
            source_name = row.source_name
        try:
            data = build_credential_records().write(
                request.user.pk,
                source_name,
                payload,
                scope=self.credential_scope,
                credential_id=credential_id,
                revoke=revoke,
            )
            return build_response(200, "success", data)
        except ValueError as error:
            return build_response(400, str(error), None)
        except CredentialConflict as error:
            return build_response(409, str(error), None)
        except CredentialUnavailable as error:
            return build_response(503, str(error), None)
        except LookupError:
            return build_response(404, "凭证不存在", None)


class SourceCredentialView(SourceCredentialsView):
    http_method_names = ["get", "put", "delete", "head", "options"]

    def get(self, request, credential_id):
        row = self.rows(request).filter(pk=credential_id).first()
        return (
            build_response(200, "success", public_credential(row))
            if row
            else build_response(404, "凭证不存在", None)
        )

    def put(self, request, credential_id):
        return self.execute(request, credential_id)

    def delete(self, request, credential_id):
        return self.execute(request, credential_id, revoke=True)


class AdminSourceCredentialsView(SourceCredentialsView):
    permission_classes = [IsAdminOperator]
    credential_scope = "system"


class AdminSourceCredentialView(SourceCredentialView):
    permission_classes = [IsAdminOperator]
    credential_scope = "system"
