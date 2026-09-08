/** @odoo-module **/
// Copyright 2022 Florian Kantelberg - initOS GmbH
// Copyright 2026 Altinkaya Enclosures
// License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import {browser} from "@web/core/browser/browser";
import {registry} from "@web/core/registry";
import {session} from "@web/session";

/** Return the appearance switch in the user menu. */
export function darkModeSwitchItem(env) {
  return {
    type: "switch",
    id: "color_scheme.switch",
    description: env._t("Dark Mode"),
    callback: () => env.services.altinkaya_theme.switchColorScheme(),
    isChecked: env.services.cookie.current.color_scheme === "dark",
    sequence: 40,
  };
}

export const colorSchemeService = {
  dependencies: ["cookie", "orm", "ui", "user"],

  /** Initialize the saved or system appearance for this browser. */
  start(env, {cookie, orm, ui, user}) {
    registry.category("user_menuitems").add("darkmode", darkModeSwitchItem);
    const preferences = session.altinkaya_theme || {};
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const isDark = preferences.device_dependent ? media.matches : preferences.dark_mode;
    const scheme = isDark ? "dark" : "light";
    if (cookie.current.color_scheme !== scheme) {
      cookie.setCookie("color_scheme", scheme);
      browser.location.reload();
    }
    if (preferences.device_dependent) {
      media.addEventListener("change", ({matches}) => {
        cookie.setCookie("color_scheme", matches ? "dark" : "light");
        browser.location.reload();
      });
    }

    return {
      /** Persist explicit choices before changing the local asset bundle. */
      async switchColorScheme() {
        const nextScheme = cookie.current.color_scheme === "dark" ? "light" : "dark";
        await orm.write("res.users", [user.userId], {
          dark_mode: nextScheme === "dark",
          dark_mode_device_dependent: false,
        });
        cookie.setCookie("color_scheme", nextScheme);
        ui.block();
        browser.location.reload();
      },
    };
  },
};

registry.category("services").add("altinkaya_theme", colorSchemeService);
