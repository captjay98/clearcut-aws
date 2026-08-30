from abc import ABC, abstractmethod


class EmailDeliveryPort(ABC):
    @abstractmethod
    async def send_invitation_email(
        self,
        recipient_email: str,
        org_name: str,
        inviter_name: str,
        raw_token: str,
    ) -> bool:
        pass
