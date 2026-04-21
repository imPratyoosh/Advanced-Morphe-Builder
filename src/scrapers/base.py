from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from src.core.network import NetworkManager


@dataclass(slots=True, frozen=True)
class DownloadResult:
    path: Path
    is_bundle: bool = False

class BaseScraper(ABC):
    def __init__(self, net: NetworkManager) -> None:
        self.net = net

    @abstractmethod
    def fetch_metadata(self, url: str) -> None:
        pass

    @abstractmethod
    def get_pkg_name(self) -> str:
        pass

    @abstractmethod
    def get_versions(self, allow_beta: bool = False) -> list[str]:
        pass

    @abstractmethod
    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        pass