import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.update_readme import (
    BLOG_END,
    BLOG_START,
    X_END,
    X_START,
    extract_blog_posts,
    extract_x_info,
    render_blog_block,
    render_x_block,
    replace_between_markers,
    update_readme,
)


class UpdateReadmeTests(unittest.TestCase):
    def test_extract_blog_posts_sorts_and_limits(self):
        html = """
        <html><body>
            <a href="/android/2026-02-01-post-a">Post A</a>
            <a href="/android/2026-03-01-post-b">Post B</a>
            <a href="/android/2026-01-15-post-c">Post C</a>
            <a href="/android">Android</a>
        </body></html>
        """
        posts = extract_blog_posts("https://www.davideagostini.com/android", html, limit=2)
        self.assertEqual(2, len(posts))
        self.assertEqual("Post B", posts[0]["title"])
        self.assertEqual("Post A", posts[1]["title"])

    def test_extract_x_info(self):
        raw = [{"name": "Davide", "screen_name": "davideagostini", "followers_count": 12345}]
        info = extract_x_info("davideagostini", raw)
        self.assertEqual("Davide", info["name"])
        self.assertEqual("davideagostini", info["screen_name"])
        self.assertEqual("12,345", info["followers"])

    def test_replace_between_markers(self):
        text = f"before\n{BLOG_START}\nold\n{BLOG_END}\nafter\n"
        out = replace_between_markers(text, BLOG_START, BLOG_END, "- new")
        self.assertIn(f"{BLOG_START}\n- new\n{BLOG_END}", out)

    def test_update_readme_end_to_end(self):
        source = f"""# Sample
{BLOG_START}
- old blog
{BLOG_END}

{X_START}
- old x
{X_END}
"""
        blog_html = """
        <a href="/android/2026-02-20-latest-post">Latest Post</a>
        <a href="/android/2026-01-01-older-post">Older Post</a>
        """
        x_payload = [{"name": "Davide Agostini", "screen_name": "davideagostini", "followers_count": 4321}]

        with tempfile.TemporaryDirectory() as tmp:
            readme_path = Path(tmp) / "README.md"
            readme_path.write_text(source, encoding="utf-8")

            with patch("scripts.update_readme.fetch_text", return_value=blog_html), patch(
                "scripts.update_readme.fetch_json", return_value=x_payload
            ):
                changed = update_readme(
                    readme_path=str(readme_path),
                    blog_url="https://www.davideagostini.com/android",
                    x_handle="davideagostini",
                    posts_limit=2,
                    today=dt.date(2026, 3, 1),
                )

            self.assertTrue(changed)
            updated = readme_path.read_text(encoding="utf-8")
            self.assertIn(render_blog_block(extract_blog_posts("https://www.davideagostini.com/android", blog_html, 2)), updated)
            self.assertIn(
                render_x_block(
                    {"name": "Davide Agostini", "screen_name": "davideagostini", "followers": "4,321", "url": "https://x.com/davideagostini"},
                    dt.date(2026, 3, 1),
                ),
                updated,
            )


if __name__ == "__main__":
    unittest.main()
