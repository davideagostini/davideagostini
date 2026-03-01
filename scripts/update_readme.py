#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


BLOG_START = "<!-- BLOG-POSTS:START -->"
BLOG_END = "<!-- BLOG-POSTS:END -->"
X_START = "<!-- X-INFO:START -->"
X_END = "<!-- X-INFO:END -->"

POST_URL_PATTERN = re.compile(r"/android/(\d{4}-\d{2}-\d{2})-[a-z0-9-]+/?$")


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict[str, str]] = []
        self._current_href = ""
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        self._current_href = ""
        for key, value in attrs:
            if key == "href" and value:
                self._current_href = value
                self._text_parts = []
                return

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._current_href:
            return
        text = " ".join("".join(self._text_parts).split())
        self.anchors.append({"href": self._current_href, "text": text})
        self._current_href = ""
        self._text_parts = []


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "readme-updater/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> object:
    return json.loads(fetch_text(url))


def extract_blog_posts(blog_url: str, html: str, limit: int = 5) -> list[dict[str, str]]:
    parser = AnchorParser()
    parser.feed(html)

    seen: set[str] = set()
    posts: list[dict[str, str]] = []
    for anchor in parser.anchors:
        raw_href = anchor["href"].strip()
        full_url = urljoin(blog_url, raw_href)
        path = "/" + full_url.split("//", 1)[-1].split("/", 1)[-1]
        if "?" in path:
            path = path.split("?", 1)[0]
        if "#" in path:
            path = path.split("#", 1)[0]
        match = POST_URL_PATTERN.search(path)
        if not match or full_url in seen:
            continue
        seen.add(full_url)
        title = anchor["text"] or path.rsplit("/", 1)[-1].replace("-", " ").title()
        posts.append({"title": title, "url": full_url, "date": match.group(1)})

    posts.sort(key=lambda item: item["date"], reverse=True)
    return posts[:limit]


def extract_x_info(x_handle: str, raw: object) -> dict[str, str]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("Unexpected X API response: expected a non-empty list")
    first = raw[0]
    if not isinstance(first, dict):
        raise ValueError("Unexpected X API response: list item is not an object")

    followers = int(first.get("followers_count", 0))
    name = str(first.get("name") or x_handle)
    screen_name = str(first.get("screen_name") or x_handle).lstrip("@")
    return {
        "name": name,
        "screen_name": screen_name,
        "followers": f"{followers:,}",
        "url": f"https://x.com/{screen_name}",
    }


def render_blog_block(posts: Iterable[dict[str, str]]) -> str:
    lines = [f"- [{p['title']}]({p['url']})" for p in posts]
    return "\n".join(lines)


def render_x_block(x_info: dict[str, str], checked_date: dt.date) -> str:
    return "\n".join(
        [
            f"- Profile: [@{x_info['screen_name']}]({x_info['url']})",
            f"- Name: {x_info['name']}",
            f"- Followers: {x_info['followers']}",
            f"- Last checked: {checked_date.isoformat()}",
        ]
    )


def replace_between_markers(content: str, start_marker: str, end_marker: str, replacement: str) -> str:
    pattern = re.compile(
        rf"({re.escape(start_marker)}\n)(.*?)(\n{re.escape(end_marker)})",
        flags=re.DOTALL,
    )
    if not pattern.search(content):
        raise ValueError(f"Could not find marker block: {start_marker} ... {end_marker}")
    return pattern.sub(rf"\1{replacement}\3", content, count=1)


def update_readme(
    readme_path: str,
    blog_url: str,
    x_handle: str,
    posts_limit: int,
    today: dt.date | None = None,
) -> bool:
    with open(readme_path, "r", encoding="utf-8") as f:
        readme = f.read()
    blog_html = fetch_text(blog_url)
    posts = extract_blog_posts(blog_url=blog_url, html=blog_html, limit=posts_limit)
    if not posts:
        raise ValueError(f"No blog posts found in {blog_url}")

    params = urlencode({"screen_names": x_handle.lstrip("@")})
    x_api = f"https://cdn.syndication.twimg.com/widgets/followbutton/info.json?{params}"
    x_info = extract_x_info(x_handle=x_handle, raw=fetch_json(x_api))
    today = today or dt.date.today()

    updated = replace_between_markers(readme, BLOG_START, BLOG_END, render_blog_block(posts))
    updated = replace_between_markers(updated, X_START, X_END, render_x_block(x_info, today))

    if updated == readme:
        return False
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(updated)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Update README blog posts and X info.")
    parser.add_argument("--readme", default="README.md", help="Path to README file")
    parser.add_argument("--blog-url", required=True, help="Blog index URL")
    parser.add_argument("--x-handle", required=True, help="X username (with or without @)")
    parser.add_argument("--posts-limit", type=int, default=5, help="Max number of blog posts to keep")
    args = parser.parse_args()

    changed = update_readme(
        readme_path=args.readme,
        blog_url=args.blog_url,
        x_handle=args.x_handle,
        posts_limit=args.posts_limit,
    )
    print("README updated." if changed else "README already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
