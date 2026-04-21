import json
from pathlib import Path
from bs4 import BeautifulSoup

from src.core.network import NetworkManager
from src.scrapers.base import BaseScraper, DownloadResult


class UptodownError(Exception):
    pass

class UptodownScraper(BaseScraper):
    def __init__(self, net: NetworkManager) -> None:
        super().__init__(net)
        self._resp_html: str = ""
        self._resp_pkg_html: str = ""

    def fetch_metadata(self, url: str) -> None:
        self._resp_html = self.net.get(f"{url}/versions")
        self._resp_pkg_html = self.net.get(f"{url}/download")

    def get_pkg_name(self) -> str:
        soup = BeautifulSoup(self._resp_pkg_html, "html.parser")
        if td := soup.select_one("tr.full:nth-child(1) > td:nth-child(3)"):
            return td.get_text(strip=True)
        raise UptodownError("Uptodown: package name not found")

    def get_versions(self, allow_beta: bool = False) -> list[str]:
        soup = BeautifulSoup(self._resp_html, "html.parser")
        return [el.get_text(strip=True) for el in soup.select(".version") if el.get_text(strip=True)]

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        if arch == "arm-v7a":
            arch = "armeabi-v7a"
        apparch = ["arm64-v8a, armeabi-v7a, x86_64", "arm64-v8a, armeabi-v7a, x86, x86_64", "arm64-v8a, armeabi-v7a"] + ([arch] if arch != "all" else [])

        soup = BeautifulSoup(self._resp_html, "html.parser")
        app_tag = soup.select_one("#detail-app-name")
        if not app_tag or not app_tag.get("data-code"):
            raise UptodownError("Uptodown: data-code not found")
        data_code = str(app_tag["data-code"])

        version_url_data = self._find_version_url(url, data_code, version)
        ver_url = f"{version_url_data['url']}/{version_url_data['extraURL']}/{version_url_data['versionID']}"
        is_bundle = version_url_data.get("kindFile") == "xapk"

        resp = self.net.get(ver_url)
        soup2 = BeautifulSoup(resp, "html.parser")
        btn_variants = soup2.select_one(".button.variants")
        data_version = btn_variants.get("data-version") if btn_variants else None

        if data_version:
            resp, is_bundle = self._pick_variant_file(url, data_code, str(data_version), apparch)

        dl_btn = BeautifulSoup(resp, "html.parser").select_one("#detail-download-button")
        if not dl_btn or not dl_btn.get("data-url"):
            raise UptodownError("Uptodown: #detail-download-button not found")

        out_path = dest.with_name(f"{dest.name}{'.apkm' if is_bundle else ''}")
        self.net.download(f"https://dw.uptodown.com/dwn/{dl_btn['data-url']}", out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)

    def _find_version_url(self, url: str, data_code: str, version: str) -> dict:
        for i in range(1, 21):
            try:
                payload = json.loads(self.net.get(f"{url}/apps/{data_code}/versions/{i}"))
            except json.JSONDecodeError as exc:
                raise UptodownError(f"Uptodown: invalid JSON on page {i}") from exc

            if match := next((e for e in payload.get("data", []) if e.get("version") == version), None):
                if not match.get("versionURL"):
                    raise UptodownError(f"Uptodown: no versionURL for version {version}")
                return match["versionURL"] | {"kindFile": match.get("kindFile", "")}

        raise UptodownError(f"Uptodown: version {version} not found in first 20 pages")

    def _pick_variant_file(self, url: str, data_code: str, data_version: str, apparch: list[str]) -> tuple[str, bool]:
        base_url = "/".join(url.split("/")[:-1])
        files_html = json.loads(self.net.get(f"{base_url}/app/{data_code}/version/{data_version}/files")).get("content", "")
        content = BeautifulSoup(files_html, "html.parser").select_one(".content")
        if not content:
            raise UptodownError("Uptodown: files content not found")

        node_arch = ""
        for child in content.children:
            if not getattr(child, "name", None):
                continue
            if "variant" not in child.get("class", []):
                node_arch = child.get_text(strip=True)
                continue
            if not node_arch:
                raise UptodownError("Uptodown: arch header missing before variant")
            if node_arch not in apparch:
                continue

            file_type_tag = child.select_one(".v-file > span")
            is_bundle = file_type_tag.get_text(strip=True) == "xapk" if file_type_tag else False
            report_tag = child.select_one(".v-report")
            if not report_tag or not report_tag.get("data-file-id"):
                raise UptodownError("Uptodown: data-file-id not found")

            resp = self.net.get(f"{url}/download/{report_tag['data-file-id']}-x")
            return resp, is_bundle

        raise UptodownError(f"Uptodown: no variant matching arch in {apparch}")
