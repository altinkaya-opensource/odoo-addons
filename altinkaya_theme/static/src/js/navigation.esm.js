/** @odoo-module **/
import {
  Component,
  onWillDestroy,
  useEffect,
  useExternalListener,
  useRef,
  useState,
} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {Dialog} from "@web/core/dialog/dialog";
import {useHotkey} from "@web/core/hotkeys/hotkey_hook";
import {useAutofocus, useBus, useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";
import {NavBar} from "@web/webclient/navbar/navbar";
import {BurgerMenu} from "@web/webclient/burger_menu/burger_menu";
import {
  collectMenuEntries,
  makeMenuEntry,
  searchMenuEntries,
} from "@altinkaya_theme/js/menu_search.esm";

let nextMenuId = 0;

/** Accept the raw base64 icons the menu service serves, or ready data URLs. */
function getIconUrl(webIconData) {
  if (!webIconData) return false;
  if (webIconData.startsWith("data:image")) return webIconData;
  const type = webIconData.startsWith("P") ? "svg+xml" : "png";
  return `data:image/${type};base64,${webIconData.replace(/\s/g, "")}`;
}

export class AltinkayaMenu extends Component {
  /** Set up the search and use Odoo's dialog keyboard/focus handling. */
  setup() {
    this.menu = useService("menu");
    this.state = useState({query: "", activeIndex: -1});
    this.searchInput = useAutofocus();
    this.results = useRef("results");
    this.resultsId = `o_altinkaya_results_${nextMenuId++}`;
    // Menus cannot change while the launcher is open: index them once.
    this.apps = this.menu.getApps().map((menu) => makeMenuEntry(menu));
    this.allEntries = null;
    this.lastSearch = {query: "", entries: this.apps};
    this.iconUrls = new Map();
    // Odoo maps Alt to Control on macOS, matching the launcher's data-hotkey.
    useHotkey("alt+h", () => this.props.close(), {
      bypassEditableProtection: true,
    });
    useEffect(
      () => {
        this.results.el
          ?.querySelector('[aria-selected="true"]')
          ?.scrollIntoView({block: "nearest", inline: "nearest"});
      },
      () => [this.state.activeIndex, this.state.query]
    );
  }

  get title() {
    return this.env._t("Applications");
  }

  get placeholder() {
    return this.env._t("Search menus...");
  }

  /** Reuse one ranking per query: the template and key handler read it repeatedly. */
  get entries() {
    const query = this.state.query.trim();
    if (this.lastSearch.query !== query) {
      this.lastSearch = {query, entries: this.searchEntries(query)};
    }
    return this.lastSearch.entries;
  }

  /** Rank the flattened menu tree, which is built on the first search. */
  searchEntries(query) {
    if (!query) return this.apps;
    if (!this.allEntries) {
      const trees = this.menu.getApps().map((menu) => this.menu.getMenuAsTree(menu.id));
      this.allEntries = collectMenuEntries(trees);
    }
    const app = this.menu.getCurrentApp();
    return searchMenuEntries(this.allEntries, query, app && app.id);
  }

  /** Close the active launcher when its backdrop is clicked. */
  handleBackdropClick(event) {
    if (this.env.dialogData.isActive && event.target.classList.contains("modal")) {
      this.props.close();
    }
  }

  /** Reset keyboard selection whenever the search text changes. */
  handleSearchInput(event) {
    this.state.query = event.target.value;
    this.state.activeIndex = -1;
  }

  /** Navigate results while retaining the search input's typing focus. */
  async handleSearchKeydown(event) {
    if (
      event.isComposing ||
      event.ctrlKey ||
      event.metaKey ||
      event.altKey ||
      event.shiftKey ||
      !["ArrowDown", "ArrowUp", "Enter"].includes(event.key)
    ) {
      return;
    }
    const entries = this.entries;
    if (!entries.length) return;
    event.preventDefault();
    event.stopPropagation();

    if (event.key === "Enter") {
      const entry =
        entries[this.state.activeIndex] || (this.state.query.trim() && entries[0]);
      if (entry && !event.repeat) await this.handleSelect(event, entry.menu);
      return;
    }

    const direction = event.key === "ArrowDown" ? 1 : -1;
    const next =
      this.state.activeIndex < 0
        ? direction > 0
          ? 0
          : entries.length - 1
        : this.state.activeIndex + direction;
    this.state.activeIndex = (next + entries.length) % entries.length;
    this.searchInput.el.focus({preventScroll: true});
  }

  /** Use the root application's identity for every submenu. */
  getApplication(menu) {
    return this.menu.getMenu(menu.appID) || menu;
  }

  /** Return the root app icon built once per app, or false for its letter fallback. */
  getIcon(menu) {
    const app = this.getApplication(menu);
    if (!this.iconUrls.has(app.id)) {
      this.iconUrls.set(app.id, getIconUrl(app.webIconData));
    }
    return this.iconUrls.get(app.id);
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
    this.altinkayaNavigation = useState({toolsOpen: false, closeMenu: null});
    onWillDestroy(() => this.altinkayaNavigation.closeMenu?.());
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

  /** Toggle one application launcher and clear its handle on every close path. */
  handleOpenApplications() {
    this.altinkayaNavigation.toolsOpen = false;
    if (this.altinkayaNavigation.closeMenu) {
      this.altinkayaNavigation.closeMenu();
      return;
    }
    this.altinkayaNavigation.closeMenu = this.altinkayaDialog.add(
      AltinkayaMenu,
      {},
      {
        onClose: () => {
          this.altinkayaNavigation.closeMenu = null;
        },
      }
    );
  },
});
