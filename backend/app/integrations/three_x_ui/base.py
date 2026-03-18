from __future__ import annotations

from abc import ABC, abstractmethod


class BaseThreeXUIAdapter(ABC):
    @abstractmethod
    def check_connection(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def list_inbounds(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def get_inbound(self, inbound_id: int) -> dict:
        raise NotImplementedError

    @abstractmethod
    def add_client(self, inbound_id: int, client_payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def update_client(self, client_id: str, inbound_id: int, client_payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def delete_client(self, inbound_id: int, client_id: str) -> None:
        raise NotImplementedError

