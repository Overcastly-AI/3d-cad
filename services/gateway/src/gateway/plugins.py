"""``/api/v1/plugins`` — the plugin manifests, proxied from documents.

Documents owns the plugins (it expands every custom feature, RESEARCH §23),
so the catalog is read from there, as the material library is
(:mod:`gateway.materials`): one owner, one hop. apps/web builds the Build
toolbar's tools and each custom feature's form from this response, so no form
is hand-written per plugin.

Auth-gated like every gateway route; the catalog is the same for every caller,
so the principal is not a scope here.
"""

from fastapi import APIRouter, Request, status
from loft_wire.plugins import PluginCatalog

from gateway.auth import CurrentUser
from gateway.parts import forward_documents
from gateway.upstream import raise_upstream_error

_SERVICE = "Documents"

router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])


@router.get("")
async def list_plugins(user: CurrentUser, http_request: Request) -> PluginCatalog:
    """Every released version of every installed plugin, by id, newest first.

    The newest version of each is flagged ``latest`` (what a new feature is
    inserted with); older ones are listed so a feature pinned to one still gets
    its form.
    """
    upstream = await forward_documents(http_request, user, "GET", "/api/v1/plugins")
    if upstream.status_code != status.HTTP_200_OK:
        raise_upstream_error(upstream, service=_SERVICE)
    return PluginCatalog.model_validate_json(upstream.content)
