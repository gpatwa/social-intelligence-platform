"""Explicit tenant authorization boundary for MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Protocol


class TenantAuthorizer(Protocol):
    def authorize(self, tenant_id: str) -> None: ...


@dataclass(frozen=True)
class StaticTenantAuthorizer:
    allowed_tenants: frozenset[str] | None = None

    def authorize(self, tenant_id: str) -> None:
        if self.allowed_tenants is not None and tenant_id not in self.allowed_tenants:
            raise PermissionError("Tenant is not authorized for this MCP session")


def authorizer_from_environment() -> StaticTenantAuthorizer:
    raw = os.environ.get("SOCIAL_INTELLIGENCE_MCP_ALLOWED_TENANTS", "").strip()
    if not raw:
        return StaticTenantAuthorizer(None)
    tenants = frozenset(value.strip() for value in raw.split(",") if value.strip())
    if not tenants:
        raise RuntimeError("SOCIAL_INTELLIGENCE_MCP_ALLOWED_TENANTS cannot be empty")
    return StaticTenantAuthorizer(tenants)
