/** @odoo-module **/
import {Component, useState} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {Dialog} from "@web/core/dialog/dialog";
import {useAutofocus, useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";
import {NavBar} from "@web/webclient/navbar/navbar";
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
    const app = this.menu.getCurrentApp();
    return this.props.mode === "sections" && app
      ? app.name
      : this.env._t("Applications");
  }

  get placeholder() {
    return this.env._t("Search menus...");
  }

  get entries() {
    const app = this.menu.getCurrentApp();
    const query = this.state.query.trim();
    const apps = this.menu.getApps();
    let entries = apps.map((menu) => ({menu, path: ""}));
    if (this.props.mode === "sections" && app) {
      entries = collectMenuEntries(this.menu.getMenuAsTree(app.id).childrenTree);
    } else if (query) {
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
    return `#menu_id=${menu.id}&action=${menu.actionID}`;
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
AltinkayaMenu.props = {close: Function, mode: String};

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
  },

  /** Open the searchable application launcher. */
  handleOpenApplications() {
    this.altinkayaDialog.add(AltinkayaMenu, {mode: "apps"});
  },

  /** Open the current application's sections on narrow screens. */
  handleOpenSections() {
    this.altinkayaDialog.add(AltinkayaMenu, {mode: "sections"});
  },
});
