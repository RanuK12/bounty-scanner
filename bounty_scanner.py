#!/usr/bin/env python3
"""
bounty_scanner.py — CLI tool to scan multiple sources for open bounties.

Usage:
    python bounty_scanner.py [--sources github,algora,opire,warpspeed]
                            [--min-bounty 100]
                            [--tag "bug"]
                            [--format table|json]
                            [--stealth]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

BOUNTY_STATUS_AVAILABLE = "available"
BOUNTY_STATUS_IN_REVIEW = "in-review"
BOUNTY_STATUS_TAKEN = "taken"

STATUS_COLORS: Dict[str, str] = {
    BOUNTY_STATUS_AVAILABLE: "green",
    BOUNTY_STATUS_IN_REVIEW: "yellow",
    BOUNTY_STATUS_TAKEN: "red",
}


@dataclass
class BountyItem:
    source: str
    title: str
    bounty: Optional[int]  # parsed dollar amount, None if unknown
    url: str
    status: str = BOUNTY_STATUS_AVAILABLE
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Dollar amount parsing
# ---------------------------------------------------------------------------

_DOLLAR_RE = re.compile(
    r"""
    (?:
        \$ \s* (?P<dollar>\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)   # $500 or $1,000.00
        |
        (?P<usd>\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?) \s* USD
        |
        bounty \s* :? \s* \$? \s* (?P<bounty>\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_dollar_amount(text: str) -> Optional[int]:
    """Return the first dollar amount found in *text*, or None."""
    if not text:
        return None
    m = _DOLLAR_RE.search(text)
    if not m:
        return None
    raw = m.group("dollar") or m.group("usd") or m.group("bounty")
    if raw is None:
        return None
    # remove commas
    raw = raw.replace(",", "")
    try:
        return int(float(raw))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_TIMEOUT = 15


def fetch_url(url: str, *, json_response: bool = False) -> Any:
    """Fetch *url* and return parsed JSON or raw text.

    Raises :class:`requests.RequestException` on failure.
    """
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    if json_response:
        return resp.json()
    return resp.text


# ---------------------------------------------------------------------------
# Source parsers
# ---------------------------------------------------------------------------

def parse_github_issues() -> List[BountyItem]:
    """Fetch open issues with label:bounty from GitHub search API."""
    url = (
        "https://api.github.com/search/issues"
        "?q=label:bounty+state:open"
        "&sort=created&order=desc&per_page=20"
    )
    data = fetch_url(url, json_response=True)
    items: List[BountyItem] = []
    for issue in data.get("items", []):
        title = issue.get("title", "")
        html_url = issue.get("html_url", "")
        repo_full = issue.get("repository_url", "").replace(
            "https://api.github.com/repos/", ""
        )
        labels = [lb["name"] for lb in issue.get("labels", [])]
        body = issue.get("body", "") or ""

        # Determine status from labels
        status = BOUNTY_STATUS_AVAILABLE
        if any("in-review" in lb.lower() or "review" in lb.lower() for lb in labels):
            status = BOUNTY_STATUS_IN_REVIEW
        if any("taken" in lb.lower() or "closed" in lb.lower() for lb in labels):
            status = BOUNTY_STATUS_TAKEN

        # Try to find dollar amount
        amount = parse_dollar_amount(title)
        if amount is None:
            amount = parse_dollar_amount(body)
        if amount is None:
            for lb in labels:
                amt = parse_dollar_amount(lb)
                if amt is not None:
                    amount = amt
                    break

        items.append(
            BountyItem(
                source="GitHub",
                title=title,
                bounty=amount,
                url=html_url,
                status=status,
                tags=labels,
            )
        )
    return items


def parse_algora() -> List[BountyItem]:
    """Scrape https://app.algora.io/bounties (public page)."""
    url = "https://app.algora.io/bounties"
    try:
        html = fetch_url(url)
    except requests.RequestException as exc:
        print(f"  [red]Algora error:[/red] {exc}", file=sys.stderr)
        return []

    soup = BeautifulSoup(html, "html.parser")
    items: List[BountyItem] = []

    # The page currently shows a sign-in wall, but we try to find any bounty cards.
    # Look for elements that might contain bounty info.
    for card in soup.select('[class*="bounty"], [class*="card"], [class*="item"]'):
        title_el = card.select_one("h2, h3, h4, [class*=title]")
        link_el = card.select_one("a[href]")
        amount_el = card.select_one("[class*=amount], [class*=price], [class*=bounty]")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        url_link = ""
        if link_el:
            href = link_el.get("href", "")
            if href.startswith("/"):
                href = "https://app.algora.io" + href
            url_link = href
        amount = None
        if amount_el:
            amount = parse_dollar_amount(amount_el.get_text(strip=True))
        if amount is None:
            amount = parse_dollar_amount(title)
        items.append(
            BountyItem(
                source="Algora",
                title=title,
                bounty=amount,
                url=url_link,
                status=BOUNTY_STATUS_AVAILABLE,
                tags=[],
            )
        )
    return items


def parse_opire() -> List[BountyItem]:
    """Scrape https://opire.dev/bounties (public page)."""
    url = "https://opire.dev/bounties"
    try:
        html = fetch_url(url)
    except requests.RequestException as exc:
        print(f"  [red]Opire error:[/red] {exc}", file=sys.stderr)
        return []

    soup = BeautifulSoup(html, "html.parser")
    items: List[BountyItem] = []

    # The page currently returns 404, but we try to find any bounty listings.
    for card in soup.select('[class*="bounty"], [class*="card"], [class*="listing"]'):
        title_el = card.select_one("h2, h3, h4, [class*=title]")
        link_el = card.select_one("a[href]")
        amount_el = card.select_one("[class*=amount], [class*=price], [class*=bounty]")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        url_link = ""
        if link_el:
            href = link_el.get("href", "")
            if href.startswith("/"):
                href = "https://opire.dev" + href
            url_link = href
        amount = None
        if amount_el:
            amount = parse_dollar_amount(amount_el.get_text(strip=True))
        if amount is None:
            amount = parse_dollar_amount(title)
        items.append(
            BountyItem(
                source="Opire",
                title=title,
                bounty=amount,
                url=url_link,
                status=BOUNTY_STATUS_AVAILABLE,
                tags=[],
            )
        )
    return items


def parse_warpspeed() -> List[BountyItem]:
    """Scrape https://warpspeed.com/bounties (public page)."""
    url = "https://warpspeed.com/bounties"
    try:
        html = fetch_url(url)
    except requests.RequestException as exc:
        print(f"  [red]Warpspeed error:[/red] {exc}", file=sys.stderr)
        return []

    soup = BeautifulSoup(html, "html.parser")
    items: List[BountyItem] = []

    for card in soup.select('[class*="bounty"], [class*="card"], [class*="listing"]'):
        title_el = card.select_one("h2, h3, h4, [class*=title]")
        link_el = card.select_one("a[href]")
        amount_el = card.select_one("[class*=amount], [class*=price], [class*=bounty]")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        url_link = ""
        if link_el:
            href = link_el.get("href", "")
            if href.startswith("/"):
                href = "https://warpspeed.com" + href
            url_link = href
        amount = None
        if amount_el:
            amount = parse_dollar_amount(amount_el.get_text(strip=True))
        if amount is None:
            amount = parse_dollar_amount(title)
        items.append(
            BountyItem(
                source="Warpspeed",
                title=title,
                bounty=amount,
                url=url_link,
                status=BOUNTY_STATUS_AVAILABLE,
                tags=[],
            )
        )
    return items


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def filter_items(
    items: List[BountyItem],
    min_bounty: Optional[int] = None,
    tag_filter: Optional[str] = None,
) -> List[BountyItem]:
    """Return items that satisfy the given filters."""
    result: List[BountyItem] = []
    for item in items:
        if min_bounty is not None and (item.bounty is None or item.bounty < min_bounty):
            continue
        if tag_filter is not None:
            tag_lower = tag_filter.lower()
            if not any(tag_lower in t.lower() for t in item.tags):
                continue
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def output_table(items: List[BountyItem]) -> None:
    """Print a rich table of bounty items."""
    console = Console()
    table = Table(title="Open Bounties", header_style="bold cyan")
    table.add_column("Source", style="dim")
    table.add_column("Title")
    table.add_column("Bounty", justify="right")
    table.add_column("URL")
    table.add_column("Status")
    table.add_column("Tags")

    for item in items:
        bounty_str = f"${item.bounty}" if item.bounty is not None else "—"
        status_color = STATUS_COLORS.get(item.status, "white")
        status_str = f"[{status_color}]{item.status}[/{status_color}]"
        tags_str = ", ".join(item.tags) if item.tags else "—"
        table.add_row(
            item.source,
            item.title,
            bounty_str,
            item.url,
            status_str,
            tags_str,
        )
    console.print(table)


def output_json(items: List[BountyItem]) -> None:
    """Print items as JSON array."""
    data = [item.to_dict() for item in items]
    print(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan multiple sources for open bounties."
    )
    parser.add_argument(
        "--sources",
        default="github,algora,opire,warpspeed",
        help="Comma-separated list of sources (github,algora,opire,warpspeed).",
    )
    parser.add_argument(
        "--min-bounty",
        type=int,
        default=None,
        help="Minimum bounty amount in USD.",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Filter by tag (case-insensitive substring match).",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format.",
    )
    parser.add_argument(
        "--stealth",
        action="store_true",
        help="Use Camofox proxy if available (not implemented).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]

    # Map source names to parser functions
    parser_map: Dict[str, Any] = {
        "github": parse_github_issues,
        "algora": parse_algora,
        "opire": parse_opire,
        "warpspeed": parse_warpspeed,
    }

    all_items: List[BountyItem] = []
    for src in sources:
        parser_fn = parser_map.get(src)
        if parser_fn is None:
            print(f"  [yellow]Unknown source '{src}', skipping.[/yellow]", file=sys.stderr)
            continue
        print(f"  Scanning {src}...", file=sys.stderr)
        try:
            items = parser_fn()
            all_items.extend(items)
        except Exception as exc:
            print(f"  [red]{src} error:[/red] {exc}", file=sys.stderr)

    filtered = filter_items(all_items, min_bounty=args.min_bounty, tag_filter=args.tag)

    if args.format == "json":
        output_json(filtered)
    else:
        output_table(filtered)


if __name__ == "__main__":
    main()
