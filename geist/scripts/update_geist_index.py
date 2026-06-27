#!/usr/bin/env python3
"""Refresh a compact local index of the official Vercel Geist docs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://vercel.com"
START_URL = "https://vercel.com/geist/introduction"
USER_AGENT = "Codex-Geist-Skill/1.0 (+https://vercel.com/geist/introduction)"

FOUNDATION_SLUGS = {"introduction", "colors", "typography", "materials"}
BRAND_SLUGS = {"brands", "nextjs", "turbo", "v0", "ai-sdk"}
RESOURCE_PREFIXES = ("geistcn-",)
RESOURCE_SLUGS = {"guidelines", "changelog"}


def clean_text(value: str) -> str:
    value = unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def slug_to_title(slug: str) -> str:
    slug = slug.split("#", 1)[0]
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def fetch(url: str, timeout: float) -> tuple[str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, "replace")
        return response.geturl(), body


@dataclass
class Link:
    text: str
    href: str


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[Link] = []
        self._href: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self._href = href
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            text = clean_text("".join(self._buffer))
            self.links.append(Link(text=text, href=self._href))
            self._href = None
            self._buffer = []


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.headings: list[dict[str, str]] = []
        self.inline_code: set[str] = set()
        self._capture_tag: str | None = None
        self._buffer: list[str] = []
        self._seen_h1 = False
        self._seen_h2 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "h3", "p", "code"}:
            self._capture_tag = tag
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture_tag:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != self._capture_tag:
            return

        text = clean_text("".join(self._buffer))
        if text:
            if tag == "h1":
                self.title = text
                self._seen_h1 = True
            elif tag in {"h2", "h3"}:
                self._seen_h2 = self._seen_h2 or tag == "h2"
                self.headings.append({"level": tag, "text": text})
            elif tag == "p" and self._seen_h1 and not self._seen_h2 and not self.description:
                if text.lower() not in {"was this helpful?", "supported."}:
                    self.description = text
            elif tag == "code" and len(text) <= 80:
                self.inline_code.add(text)

        self._capture_tag = None
        self._buffer = []


def parse_links(html: str) -> list[Link]:
    parser = LinkParser()
    parser.feed(html)
    return parser.links


def parse_page(html: str) -> dict[str, object]:
    parser = PageParser()
    parser.feed(html)

    packages = sorted(set(re.findall(r"@vercel/geistcn/[A-Za-z0-9_./-]+", html)))
    inline_code = sorted(
        code for code in parser.inline_code if code and not code.startswith("http")
    )

    return {
        "title": parser.title,
        "description": parser.description,
        "headings": parser.headings,
        "inline_code": inline_code[:80],
        "packages": packages,
    }


def classify(slug: str) -> str:
    page_slug = slug.split("#", 1)[0]
    if page_slug in FOUNDATION_SLUGS:
        return "foundations"
    if page_slug in BRAND_SLUGS:
        return "brands"
    if page_slug in RESOURCE_SLUGS or page_slug.startswith(RESOURCE_PREFIXES):
        return "resources"
    return "components"


def item_from_link(link: Link, order: int) -> dict[str, object] | None:
    absolute_url = urljoin(BASE_URL, link.href)
    parsed = urlparse(absolute_url)

    if parsed.netloc != "vercel.com" or not parsed.path.startswith("/geist/"):
        return None

    page_slug = parsed.path.rsplit("/", 1)[-1]
    fragment = parsed.fragment or None
    slug = f"{page_slug}#{fragment}" if fragment else page_slug

    name = clean_text(link.text)
    if not name or len(name) > 42:
        name = slug_to_title(slug)

    if name.lower() in {"previous", "next", "give feedback"}:
        return None

    return {
        "name": name,
        "slug": slug,
        "page_slug": page_slug,
        "path": parsed.path,
        "fragment": fragment,
        "url": absolute_url,
        "category": classify(slug),
        "order": order,
    }


def collect_items(html: str) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str | None], dict[str, object]] = {}

    for order, link in enumerate(parse_links(html)):
        item = item_from_link(link, order)
        if item is None:
            continue

        key = (str(item["path"]), item["fragment"] if isinstance(item["fragment"], str) else None)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = item
            continue

        current_name = str(item["name"])
        old_name = str(existing["name"])
        if len(current_name) < len(old_name):
            item["order"] = existing["order"]
            by_key[key] = item

    return sorted(by_key.values(), key=lambda item: int(item["order"]))


def selected_page_paths(
    items: Iterable[dict[str, object]], slugs: set[str] | None, details: bool
) -> set[str]:
    if details and not slugs:
        return {str(item["path"]) for item in items}

    if not slugs:
        return set()

    paths: set[str] = set()
    for item in items:
        page_slug = str(item["page_slug"])
        slug = str(item["slug"])
        name_slug = str(item["name"]).lower().replace(" ", "-")
        if page_slug in slugs or slug in slugs or name_slug in slugs:
            paths.add(str(item["path"]))
    return paths


def fetch_details(
    paths: set[str], timeout: float, max_workers: int
) -> dict[str, dict[str, object]]:
    details: dict[str, dict[str, object]] = {}
    if not paths:
        return details

    def load(path: str) -> tuple[str, dict[str, object]]:
        final_url, html = fetch(urljoin(BASE_URL, path), timeout=timeout)
        page = parse_page(html)
        page["final_url"] = final_url
        return path, page

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(load, path): path for path in sorted(paths)}
        for future in as_completed(futures):
            path = futures[future]
            try:
                resolved_path, page = future.result()
            except Exception as exc:  # noqa: BLE001 - preserve all fetch errors in output.
                details[path] = {"error": str(exc)}
            else:
                details[resolved_path] = page

    return details


def attach_details(
    items: list[dict[str, object]], details: dict[str, dict[str, object]]
) -> None:
    for item in items:
        detail = details.get(str(item["path"]))
        if not detail:
            continue
        item.update(
            {
                "title": detail.get("title", ""),
                "description": detail.get("description", ""),
                "headings": detail.get("headings", []),
                "inline_code": detail.get("inline_code", []),
                "packages": detail.get("packages", []),
                "final_url": detail.get("final_url", item["url"]),
            }
        )
        if "error" in detail:
            item["error"] = detail["error"]


def load_cached_details(output_dir: Path) -> dict[str, dict[str, object]]:
    index_path = output_dir / "geist-index.json"
    if not index_path.exists():
        return {}

    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    cached: dict[str, dict[str, object]] = {}
    for item in payload.get("items", []):
        if not isinstance(item, dict) or "path" not in item:
            continue
        path = str(item["path"])
        cached[path] = {
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "headings": item.get("headings", []),
            "inline_code": item.get("inline_code", []),
            "packages": item.get("packages", []),
            "final_url": item.get("final_url", item.get("url", "")),
        }
    return cached


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def markdown_table(items: list[dict[str, object]], category: str) -> list[str]:
    rows = [f"## {category.capitalize()}", "", "| Name | URL | Page Sections | Packages |", "| --- | --- | --- | --- |"]
    filtered = [item for item in items if item["category"] == category]
    if not filtered:
        rows.append("| _None found_ | | | |")
        rows.append("")
        return rows

    for item in filtered:
        headings = item.get("headings", [])
        heading_text = ""
        if isinstance(headings, list):
            heading_text = ", ".join(
                str(heading.get("text", "")) for heading in headings[:8] if isinstance(heading, dict)
            )
        packages = ", ".join(str(value) for value in item.get("packages", [])[:4])
        rows.append(
            f"| {item['name']} | {item['url']} | {heading_text or '-'} | {packages or '-'} |"
        )
    rows.append("")
    return rows


def write_markdown(path: Path, payload: dict[str, object]) -> None:
    items = payload["items"]
    assert isinstance(items, list)
    lines = [
        "# Geist Index",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Source: `{payload['source']}`",
        "",
        "Refresh:",
        "",
        "```bash",
        "python3 ~/.codex/skills/geist/scripts/update_geist_index.py --details",
        "```",
        "",
    ]
    for category in ("foundations", "resources", "brands", "components"):
        lines.extend(markdown_table(items, category))
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=START_URL, help="Official Geist entry page")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "references",
        help="Directory for geist-index.json and geist-index.md",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Fetch detail metadata for every discovered page",
    )
    parser.add_argument(
        "--slugs",
        help="Comma-separated page/component slugs to detail, such as button,input,modal",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-workers", type=int, default=8)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    source_url, html = fetch(args.source, timeout=args.timeout)
    items = collect_items(html)
    cached_details = load_cached_details(args.output_dir)
    attach_details(items, cached_details)

    requested_slugs = None
    if args.slugs:
        requested_slugs = {slug.strip().lower() for slug in args.slugs.split(",") if slug.strip()}

    paths = selected_page_paths(items, requested_slugs, args.details)
    details = fetch_details(paths, timeout=args.timeout, max_workers=max(1, args.max_workers))
    attach_details(items, details)

    payload: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source_url,
        "details_fetched": bool(paths),
        "cached_detail_pages": len(cached_details),
        "requested_slugs": sorted(requested_slugs) if requested_slugs else [],
        "item_count": len(items),
        "items": items,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "geist-index.json", payload)
    write_markdown(args.output_dir / "geist-index.md", payload)

    print(f"Wrote {len(items)} Geist entries to {args.output_dir}")
    if paths:
        print(f"Fetched detail metadata for {len(paths)} page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
