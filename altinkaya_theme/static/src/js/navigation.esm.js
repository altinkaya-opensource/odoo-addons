/** @odoo-module **/
import {Component, useExternalListener, useState} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {Dialog} from "@web/core/dialog/dialog";
import {useAutofocus, useBus, useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";
import {NavBar} from "@web/webclient/navbar/navbar";
import {BurgerMenu} from "@web/webclient/burger_menu/burger_menu";
import {searchMenuEntries} from "@altinkaya_theme/js/menu_search.esm";

/** Flatten the accessible menu tree, keeping group names as context. */
function collectMenuEntries(nodes, parents = []) {
  const entries = [];
  for (const menu of nodes) {
    if (menu.actionID) {
      entries.push({menu, path: parents.join(" / ")});
    }
    entries.push(...collectMenuEntries(menu.childrenTree, [...parents, menu.name]));
  }
  return entries;
}

export class AltinkayaMenu extends Component {
  /** Set up the search and use Odoo's dialog keyboard/focus handling. */
  setup() {
    this.menu = useService("menu");
    this.state = useState({query: ""});
    useAutofocus();
  }

  get title() {
    return this.env._t("Applications");
  }

  get placeholder() {
    return this.env._t("Search menus...");
  }

  get entries() {
    const app = this.menu.getCurrentApp();
    const query = this.state.query.trim();
    const apps = this.menu.getApps();
    let entries = apps.map((menu) => ({menu, path: ""}));
    if (query) {
      entries = collectMenuEntries(
        apps.map((menu) => this.menu.getMenuAsTree(menu.id))
      );
    }
    return searchMenuEntries(entries, query, app && app.id);
  }

  /** Use the root application's identity for every submenu. */
  getApplication(menu) {
    return this.menu.getMenu(menu.appID) || menu;
  }

  /** Return the root app icon, or use its letter fallback. */
  getIcon(menu) {
    const app = this.getApplication(menu);
    if (!app.webIconData) return false;
    if (app.webIconData.startsWith("data:image")) return app.webIconData;
    const type = app.webIconData.startsWith("P") ? "svg+xml" : "png";
    return `data:image/${type};base64,${app.webIconData.replace(/\s/g, "")}`;
  }

  /** Keep ordinary links usable in a separate browser tab. */
  getHref(menu) {
    return `#menu_id=${menu.id}${menu.actionID ? `&action=${menu.actionID}` : ""}`;
  }

  /** Navigate through the existing action service, preserving access rules. */
  async handleSelect(event, menu) {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    await this.menu.selectMenu(menu);
    this.props.close();
  }
}
AltinkayaMenu.template = "altinkaya_theme.Menu";
AltinkayaMenu.components = {Dialog};
AltinkayaMenu.props = {close: Function};

// Render the native mobile panel beside the tools toggle, exactly once.
Object.assign(NavBar.components, {AltinkayaBurgerMenu: BurgerMenu});

patch(NavBar.prototype, "altinkaya_theme.navigation", {
  /** Mark only explicit debug sessions served from localhost. */
  isLocalDebug() {
    const url = new URL(browser.location.href);
    return (
      url.hostname === "localhost" &&
      ["true", "assets"].includes(url.searchParams.get("debug"))
    );
  },

  /** Initialize the native dialog service.
   *
   * @override
   */
  setup() {
    this._super(...arguments);
    this.altinkayaDialog = useService("dialog");
    this.altinkayaNavigation = useState({toolsOpen: false});
    useBus(this.env.bus, "ACTION_MANAGER:UPDATE", () => {
      this.altinkayaNavigation.toolsOpen = false;
    });
    useExternalListener(window, "keydown", (event) => {
      if (event.key === "Escape") this.altinkayaNavigation.toolsOpen = false;
    });
  },

  /** Toggle the compact mobile tray without recreating systray components. */
  handleToggleTools() {
    this.altinkayaNavigation.toolsOpen = !this.altinkayaNavigation.toolsOpen;
  },

  /** Open the searchable application launcher. */
  handleOpenApplications() {
    this.altinkayaNavigation.toolsOpen = false;
    this.altinkayaDialog.add(AltinkayaMenu, {});
  },
});
