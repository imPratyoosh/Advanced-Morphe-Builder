import re
from pathlib import Path
from bs4 import BeautifulSoup

from src.core.network import NetworkManager
from src.scrapers.base import BaseScraper, DownloadResult


class APKMirrorError(Exception):
    pass

class APKMirrorScraper(BaseScraper):
    def __init__(self, net: NetworkManager) -> None:
        super().__init__(net)
        self._resp_html: str = ""
        self._category: str = ""

    def fetch_metadata(self, url: str) -> None:
        self._resp_html = self.net.get(url)
        self._category = url.rstrip("/").split("/")[-1]

    def get_pkg_name(self) -> str:
        m = re.search(r"play\.google\.com/store/apps/details\?id=([\w.]+)", self._resp_html)
        if m:
            return m.group(1)
        raise APKMirrorError("APKMirror: package name not found in page")

    def get_versions(self, allow_beta: bool = False) -> list[str]:
        html = self.net.get(f"https://www.apkmirror.com/uploads/?appcategory={self._category}")
        soup = BeautifulSoup(html, "html.parser")
        versions = [v for val in soup.select("span.infoSlide-name + span.infoSlide-value") if (v := val.get_text(strip=True))]

        if allow_beta:
            return versions

        return [v for v in versions if not re.search(r"beta|alpha", v, re.I)]

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        if arch == "arm-v7a":
            arch = "armeabi-v7a"

        soup = BeautifulSoup(self._resp_html, "html.parser")
        h1 = soup.select_one("h1.marginZero")
        apkmname = re.sub(r"[^a-z0-9-]", "", (h1.get_text(strip=True).lower() if h1 else "").replace(" ", "-"))
        ver_dashed = version.replace(".", "-").replace(" ", "-")
        release_url = f"{url.rstrip('/')}/{apkmname}-{ver_dashed}-release/"
        resp = self.net.get(release_url)

        is_bundle = False
        if BeautifulSoup(resp, "html.parser").select_one("div.table-row.headerFont:last-child"):
            dl_url = self._pick_variant(resp, dpi, arch)
            if dl_url is None:
                raise APKMirrorError(f"APKMirror: no matching variant for {version}/{arch}")
            resp = self.net.get(dl_url[0])
            is_bundle = dl_url[1] == "BUNDLE"

        btn = BeautifulSoup(resp, "html.parser").select_one("a.btn")
        if not btn or not btn.get("href"):
            raise APKMirrorError("APKMirror: download button not found")

        resp = self.net.get(_absolute(str(btn["href"])))
        a_tag = BeautifulSoup(resp, "html.parser").select_one("span > a[rel=nofollow]")
        if not a_tag or not a_tag.get("href"):
            raise APKMirrorError("APKMirror: final download link not found")

        suffix = ".apkm" if is_bundle else ""
        out_path = dest.with_name(f"{dest.name}{suffix}")
        self.net.download(_absolute(str(a_tag["href"])), out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)

    def _pick_variant(self, html: str, dpi: str, arch: str) -> tuple[str, str] | None:
        for bt in ("APK", "BUNDLE"):
            if url_found := self._search(html, dpi, arch, bt):
                return url_found, bt

        rows = BeautifulSoup(html, "html.parser").select("div.table-row.headerFont")
        for row in reversed(rows):
            link = row.select_one("div.table-cell:first-child > a")
            if not link or not link.get("href"):
                continue
            badge = row.select_one(".apkm-badge")
            b_type = badge.get_text(strip=True).upper() if badge else "APK"
            return _absolute(str(link["href"])), b_type

        return None

    def _search(self, html: str, dpi: str, arch: str, bundle_type: str) -> str:
        apparch = ["universal", "noarch", "arm64-v8a + armeabi-v7a"] + ([arch] if arch != "all" else [])
        appdpi = ["nodpi", "anydpi", "120-640dpi"] + ([dpi] if dpi else [])
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("div.table-row.headerFont")

        for row in reversed(rows):
            link = row.select_one("div.table-cell:first-child > a")
            if not link or not link.get("href"):
                continue
            href = _absolute(str(link["href"]))
            spans = [c for c in row.children if getattr(c, "name", None) == "span"]
            span_texts = [s.get_text(strip=True) for s in spans[2:]]
            if len(span_texts) < 4:
                continue
            if span_texts[2] == bundle_type and span_texts[5 - 2] in appdpi and span_texts[3 - 2] in apparch:
                return href

        return ""

def _absolute(href: str) -> str:
    return href if href.startswith(("http://", "https://")) else f"https://www.apkmirror.com{href}"
