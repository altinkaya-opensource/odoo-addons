# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests import common

from ..hooks import pre_init_hook
from ..models import ir_http


class TestTheme(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = common.new_test_user(
            cls.env, login="altinkaya_theme_test", groups="base.group_user"
        )

    def test_user_can_change_own_preferences(self):
        user = self.user.with_user(self.user)
        user.write({"dark_mode": True, "dark_mode_device_dependent": True})
        self.assertTrue(user.dark_mode)
        self.assertTrue(user.dark_mode_device_dependent)

    def test_cookie_follows_saved_appearance(self):
        request = SimpleNamespace(
            env=self.user.with_user(self.user).env,
            httprequest=SimpleNamespace(cookies={}),
        )
        with patch.object(ir_http, "request", request):
            for dark_mode in (False, True):
                self.user.write({"dark_mode": dark_mode})
                scheme = "dark" if dark_mode else "light"
                response = MagicMock()
                request.httprequest.cookies = {}
                self.env["ir.http"]._set_color_scheme(response)
                response.set_cookie.assert_called_once_with("color_scheme", scheme)
                response.reset_mock()
                request.httprequest.cookies = {"color_scheme": scheme}
                self.env["ir.http"]._set_color_scheme(response)
                response.set_cookie.assert_not_called()

    def test_system_preference_does_not_overwrite_browser_choice(self):
        self.user.write({"dark_mode_device_dependent": True})
        request = SimpleNamespace(
            env=self.user.with_user(self.user).env,
            httprequest=SimpleNamespace(cookies={"color_scheme": "dark"}),
        )
        response = MagicMock()
        with patch.object(ir_http, "request", request):
            self.env["ir.http"]._set_color_scheme(response)
        response.set_cookie.assert_not_called()

    def test_assets_are_scoped_to_backend_bundles(self):
        assets = self.env["ir.asset"]
        for bundle in ("web.assets_backend", "web.dark_mode_assets_backend"):
            paths = [
                row[0].lstrip("/") for row in assets._get_asset_paths(bundle, css=True)
            ]
            self.assertIn("altinkaya_theme/static/src/scss/backend.scss", paths)
            primary = paths.index(
                "altinkaya_theme/static/src/scss/primary_variables.scss"
            )
            self.assertLess(
                primary, paths.index("web/static/src/scss/primary_variables.scss")
            )
            dark = "altinkaya_theme/static/src/scss/dark_variables.scss"
            if "dark_mode" in bundle:
                self.assertLess(paths.index(dark), primary)
            else:
                self.assertNotIn(dark, paths)
        for bundle in ("web.assets_frontend", "web.report_assets_common"):
            paths = [row[0] for row in assets._get_asset_paths(bundle, css=True)]
            self.assertFalse([path for path in paths if "altinkaya_theme/" in path])


class TestLegacyMigration(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.legacy = self.env["ir.module.module"].search(
            [("name", "=", "web_dark_mode")]
        )
        if not self.legacy:
            self.legacy = self.env["ir.module.module"].create({"name": "web_dark_mode"})
        self.legacy.write({"state": "installed"})
        self.view = self.env["ir.ui.view"].create(
            {
                "name": "Theme migration test",
                "model": "res.users",
                "arch": '<form><field name="name"/></form>',
            }
        )
        self.data = self.env["ir.model.data"].create(
            {
                "module": "web_dark_mode",
                "name": "test_theme_legacy_view",
                "model": "ir.ui.view",
                "res_id": self.view.id,
            }
        )

    def test_takeover_preserves_records_and_preferences(self):
        self.env.user.write({"dark_mode": True, "dark_mode_device_dependent": True})
        pre_init_hook(self.env.cr)
        self.assertEqual(self.legacy.state, "uninstalled")
        self.assertEqual(self.data.module, "altinkaya_theme")
        self.assertEqual(self.data.res_id, self.view.id)
        self.assertTrue(self.view.exists())
        self.assertTrue(self.env.user.dark_mode)
        self.assertTrue(self.env.user.dark_mode_device_dependent)
        pre_init_hook(self.env.cr)
        self.assertEqual(self.data.module, "altinkaya_theme")

    def test_takeover_rejects_installed_dependents(self):
        self.env["ir.module.module"].create(
            {
                "name": "test_theme_dependent",
                "state": "installed",
                "dependencies_id": [(0, 0, {"name": "web_dark_mode"})],
            }
        )
        with self.assertRaises(UserError):
            pre_init_hook(self.env.cr)
        self.assertEqual(self.legacy.state, "installed")
        self.assertEqual(self.data.module, "web_dark_mode")

    def test_takeover_rejects_conflicting_identifiers(self):
        self.env["ir.model.data"].create(
            {
                "module": "altinkaya_theme",
                "name": self.data.name,
                "model": "ir.ui.view",
                "res_id": self.view.id,
            }
        )
        with self.assertRaises(UserError):
            pre_init_hook(self.env.cr)
        self.assertEqual(self.legacy.state, "installed")
        self.assertEqual(self.data.module, "web_dark_mode")
