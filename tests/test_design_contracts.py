import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
MAIN = ROOT / "main.py"


class DesignContractsTest(unittest.TestCase):
    def read_template(self, name: str) -> str:
        return (TEMPLATES / name).read_text(encoding="utf-8")

    def test_public_page_uses_external_assets(self):
        html = self.read_template("public.html")

        self.assertIn('/static/css/public.css', html)
        self.assertIn('/static/js/public.js', html)
        self.assertNotIn("<style>", html)

    def test_public_page_keeps_creator_and_influencer_copy_workflow(self):
        html = self.read_template("public.html")

        required_fragments = [
            "creator_name",
            "creator_id",
            "start_time",
            "influencer_copy",
            "Copy for Influencer",
            "CC ID",
            "Starts",
        ]
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)

        self.assertNotIn("No commission program assigned", html)

    def test_budget_field_is_presented_as_orders(self):
        public_html = self.read_template("public.html")
        admin_html = self.read_template("admin.html")
        main_py = MAIN.read_text(encoding="utf-8")

        self.assertIn("d.budget", public_html)
        self.assertIn("Orders", public_html)
        self.assertNotIn("${{ d.budget", public_html)

        self.assertIn('lines.append(f"Orders: {deal.budget}")', main_py)
        self.assertNotIn('lines.append(f"Budget: ${deal.budget}")', main_py)
        self.assertIn('"orders"', main_py)

        self.assertIn("<th>Orders</th>", admin_html)
        self.assertIn("{{ d.budget }} orders", admin_html)
        self.assertIn("<label>Orders</label>", admin_html)
        self.assertNotIn("<th>Budget</th>", admin_html)
        self.assertNotIn("${{ d.budget }}", admin_html)

    def test_public_cards_use_aligned_slots_and_compact_time_row(self):
        public_html = self.read_template("public.html")
        public_css = (STATIC / "css/public.css").read_text(encoding="utf-8")

        required_template_slots = [
            "card-image-slot",
            "card-cat-slot",
            "card-title-slot",
            "creator-slot",
            "price-slot",
            "detail-slot",
            "time-slot",
            "copy-slot",
            "action-slot",
            "deal-time-row",
            "time-separator",
        ]
        for fragment in required_template_slots:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, public_html)

        self.assertIn("grid-template-rows", public_css)
        self.assertIn(".deal-time-row", public_css)
        self.assertIn("font-size: 10px", public_css)
        self.assertIn("flex-wrap: nowrap", public_css)
        self.assertIn("gap: 6px", public_css)
        self.assertNotIn("minmax(58px", public_css)
        self.assertNotIn("minmax(48px", public_css)
        self.assertNotIn("minmax(66px", public_css)

    def test_admin_pages_share_responsive_admin_styles(self):
        for template_name in ("admin.html", "categories.html", "settings.html"):
            with self.subTest(template=template_name):
                html = self.read_template(template_name)
                self.assertIn('/static/css/admin.css', html)
                self.assertNotIn("<style>", html)

    def test_admin_tables_have_scroll_shells(self):
        for template_name in ("admin.html", "categories.html", "settings.html"):
            with self.subTest(template=template_name):
                html = self.read_template(template_name)
                self.assertIn('class="table-shell"', html)

    def test_static_design_assets_are_local(self):
        for asset in ("css/public.css", "css/admin.css", "js/public.js"):
            with self.subTest(asset=asset):
                content = (STATIC / asset).read_text(encoding="utf-8")
                self.assertNotIn("https://", content)
                self.assertNotIn("http://", content)


if __name__ == "__main__":
    unittest.main()
