import re
from pathlib import Path
from bs4 import BeautifulSoup

from src.core.network import NetworkManager
from src.scrapers.base import BaseScraper, DownloadResult

_ARCH_SUFFIX = re.compile(r"-(?:all|arm64-v8a|arm-v7a)\.(?:apk|apkm|xapk)$")

class ArchiveError(Exception):
    pass

class ArchiveScraper(BaseScraper):
    def __init__(self, net: NetworkManager) -> None:
        super().__init__(net)
        self._file_list: list[str] = []
        self._pkg_name: str = ""

    def fetch_metadata(self, url: str) -> None:
        html = self.net.get(url)
        soup = BeautifulSoup(html, "html.parser")
        self._file_list = [
            a["href"] for a in soup.find_all("a", href=True)
            if not str(a["href"]).startswith(("?", "/", "http"))
        ]
        self._pkg_name = url.rstrip("/").split("/")[-1]

    def get_pkg_name(self) -> str:
        return self._pkg_name

    def get_versions(self, allow_beta: bool = False) -> list[str]:
        versions: list[str] = []
        for fname in self._file_list:
            parts = fname.split("-", 1)
            if len(parts) < 2:
                continue
            if ver_part := _ARCH_SUFFIX.sub("", parts[1]):
                versions.append(ver_part)
        return list(dict.fromkeys(versions))

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        version = version.replace(" ", "")
        arch = arch.replace(" ", "")
        pattern = re.compile(rf"(?<![.\d]){re.escape(version.lstrip('v'))}-{re.escape(arch)}")
        match = next((f for f in self._file_list if pattern.search(f)), None)
        if not match:
            raise ArchiveError(f"Archive: no file matching version='{version}' arch='{arch}' in {url}")

        is_bundle = match.endswith((".apkm", ".xapk"))
        out_path = dest.with_name(f"{dest.name}{'.apkm' if is_bundle else ''}")
        self.net.download(f"{url.rstrip('/')}/{match}", out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)
