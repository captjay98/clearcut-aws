from typing import Protocol
from uuid import UUID


class WebMonitorPort(Protocol):
    async def create_monitor(
        self,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        target_url: str,
    ) -> str:
        """Create an external monitor and return external monitor ID."""
        ...

    async def cancel_monitor(self, external_monitor_id: str) -> None:
        """Cancel an external monitor."""
        ...

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify HMAC-SHA256 webhook signature."""
        ...
