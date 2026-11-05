"""D17-B02 — storefront section fields must survive a create as well as an edit.

`storefront_sections` keeps everything visual in the single JSONB `content`
column, but the admin editors post `subtitle` / `image_url` / `cta_text` /
`cta_url` / `placement` as flat body keys. PATCH folded them into `content`;
POST did not, so a newly created promo saved its title and silently dropped
its image and CTA — the section then rendered empty on the live site.

These tests pin the folding helper that both routes now share so create and
update can never drift apart again.
"""

import os
import unittest

for _k, _v in (
    ("SUPABASE_URL", "https://example.supabase.co"),
    ("SUPABASE_ANON_KEY", "test-anon"),
    ("SUPABASE_SERVICE_ROLE_KEY", "test-service"),
    ("SUPABASE_JWT_SECRET", "test-jwt"),
    ("SESSION_SECRET", "test-session"),
    ("JWT_SECRET", "test-jwt-secret"),
):
    os.environ.setdefault(_k, _v)

from app.routes.storefront import (  # noqa: E402  (env must be set first)
    _SECTION_CONTENT_ALIASES,
    _section_content,
    _section_content_touched,
)


class TestSectionContentFolding(unittest.TestCase):
    def test_flat_fields_are_folded_into_content(self):
        """The exact body the promo/popup editor sends on create."""
        out = _section_content({
            "title": "Squad Feast",
            "subtitle": "Order with your squad",
            "image_url": "https://cdn.example/x.jpg",
            "cta_text": "Start a squad",
            "cta_url": "/events",
            "placement": "home",
        })
        self.assertEqual(out["subtitle"], "Order with your squad")
        self.assertEqual(out["image_url"], "https://cdn.example/x.jpg")
        self.assertEqual(out["cta_text"], "Start a squad")
        self.assertEqual(out["cta_url"], "/events")
        self.assertEqual(out["placement"], "home")

    def test_legacy_aliases_are_written(self):
        """The live hero reads content.subheadline / content.cta_link."""
        out = _section_content({"subtitle": "S", "cta_url": "/menu"})
        for canonical, alias in _SECTION_CONTENT_ALIASES.items():
            if canonical in ("subtitle", "cta_url"):
                self.assertEqual(out[alias], out[canonical])

    def test_body_field_is_folded(self):
        self.assertEqual(_section_content({"body": "Long copy"})["body"], "Long copy")

    def test_explicit_content_wins_over_base_but_flat_wins_over_content(self):
        out = _section_content({"content": {"a": 1, "image_url": "flat-overrides"}}, {"b": 2, "a": 0})
        self.assertEqual(out["b"], 2)            # existing content preserved
        self.assertEqual(out["a"], 1)            # posted content wins
        self.assertEqual(out["image_url"], "flat-overrides")

    def test_flat_field_overrides_the_same_key_in_content(self):
        """Editors send both shapes; the flat value is the one the admin typed last."""
        out = _section_content({"content": {"image_url": "old"}, "image_url": "new"})
        self.assertEqual(out["image_url"], "new")

    def test_null_content_is_rejected(self):
        """content: null must surface as 400, not a NOT NULL 500 (D17-B13)."""
        self.assertIsNone(_section_content({"content": None}))

    def test_empty_body_yields_empty_content(self):
        self.assertEqual(_section_content({}), {})

    def test_touched_only_for_content_keys(self):
        self.assertFalse(_section_content_touched({"title": "T"}))
        self.assertFalse(_section_content_touched({"sort_order": 1}))
        self.assertTrue(_section_content_touched({"image_url": "u"}))
        self.assertTrue(_section_content_touched({"placement": "home"}))
        self.assertTrue(_section_content_touched({"content": {}}))


if __name__ == "__main__":
    unittest.main()
