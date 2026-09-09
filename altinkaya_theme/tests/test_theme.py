# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from odoo import api
from odoo.exceptions import UserError
from odoo.tests import common

from ..hooks import pre_init_hook
from ..models import ir_http

LAUNCHER_CHECK = """
(async () => {
    const until = async (check, label) => {
        for (let i = 0; i < 100; i++) {
            const value = check();
            if (value) return value;
            await new Promise((resolve) => setTimeout(resolve, 100));
        }
        throw new Error("timeout: " + label);
    };
    document.querySelector(".o_altinkaya_launcher_button").click();
    const input = await until(
        () => document.querySelector(".o_altinkaya_menu_search input"),
        "launcher search field"
    );
    if (!document.querySelector(".o_altinkaya_app_grid .o_altinkaya_app_icon")) {
        throw new Error("no application tiles rendered");
    }
    input.value = "user";
    input.dispatchEvent(new Event("input", {bubbles: true}));
    await until(
        () => document.querySelector(".o_altinkaya_sections_list"), "search results"
    );
    const names = [...document.querySelectorAll(".o_altinkaya_app strong")].map(
        (el) => el.textContent
    );
    if (!names.some((name) => /user/i.test(name))) {
        throw new Error("Users menu missing from: " + names.join(", "));
    }
    const arrowDown = new KeyboardEvent("keydown", {key: "ArrowDown", bubbles: true});
    input.dispatchEvent(arrowDown);
    await until(
        () => document.querySelector(".o_altinkaya_app[aria-selected='true']"),
        "keyboard selection"
    );
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""


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
        self.user.write({"dark_mode_device_dependent": False})
        request = SimpleNamespace(
            env=self.user.with_user(self.user).env,
            session=SimpleNamespace(uid=self.user.id),
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
        request = SimpleNamespace(
            env=self.user.with_user(self.user).env,
            session=SimpleNamespace(uid=self.user.id),
            httprequest=SimpleNamespace(cookies={"color_scheme": "dark"}),
        )
        response = MagicMock()
        with patch.object(ir_http, "request", request):
            self.env["ir.http"]._set_color_scheme(response)
        response.set_cookie.assert_not_called()

    def test_anonymous_requests_get_no_cookie(self):
        request = SimpleNamespace(
            env=self.env(user=self.env.ref("base.public_user")),
            session=SimpleNamespace(uid=None),
            httprequest=SimpleNamespace(cookies={}),
        )
        response = MagicMock()
        with patch.object(ir_http, "request", request):
            self.env["ir.http"]._set_color_scheme(response)
        response.set_cookie.assert_not_called()

    def test_auth_none_routes_read_the_session_user(self):
        self.user.write({"dark_mode": True, "dark_mode_device_dependent": False})
        request = SimpleNamespace(
            env=api.Environment(self.env.cr, None, {}),
            session=SimpleNamespace(uid=self.user.id),
            httprequest=SimpleNamespace(cookies={"color_scheme": "light"}),
        )
        response = MagicMock()
        with patch.object(ir_http, "request", request):
            self.env["ir.http"]._set_color_scheme(response)
        response.set_cookie.assert_called_once_with("color_scheme", "dark")

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


@common.tagged("post_install", "-at_install")
class TestLauncherUi(common.HttpCase):
    def test_launcher_search_and_keyboard_selection(self):
        self.env.ref("base.user_admin").write(
            {"dark_mode": False, "dark_mode_device_dependent": False}
        )
        self.browser_js(
            "/web",
            LAUNCHER_CHECK,
            "document.querySelector('.o_action_manager > *') !== null",
            login="admin",
            timeout=300,
        )
