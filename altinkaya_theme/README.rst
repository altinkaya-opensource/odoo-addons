Altinkaya Theme
===============

A shared backend design for Odoo 16 Community with modern light and dark
palettes. Forms, navigation, buttons, notebooks, chatter, badges and alerts
use the same component rules in both appearances. A searchable application
launcher and a mobile section menu replace web_responsive. Uninstall
``web_responsive``, ``web_company_color`` and ``web_theme_classic`` before
installing or upgrading this theme: backend colors and field borders are
provided by this addon in both appearances. Website and report bundles do
not receive the backend component styles.

Refresh the Apps list after updating addon files so Odoo reloads the module
exclusions; a command-line upgrade alone may leave the old exclusions stored.

Neutral surfaces distinguish the workspace, form and chatter without tinting
every area blue. Field labels remain opaque, including readonly and empty
fields; links and active controls use the blue accent. List headers and
alternating rows have separate tones with subtle column separators.

Editable fields use muted fills, uniform thin borders and a single focus
ring. Required fields have a subtle purple tint and a narrow leading edge.
Title fields keep the same visible border as other editable fields; nested
inputs share one outer border.

On phones the navbar stays on one line; its tools tray keeps all systray
integrations accessible. The native mobile panel button stays directly in
the navbar beside the tools button; the current app name is a plain title.
The application launcher fills the viewport even with ``web_dialog_size``
installed. It uses a large-icon grid and searches all submenus. Mobile search,
filters, the view switcher and the user menu use Odoo's native components.
Touch controls, full-width forms and scrollable notebook tabs follow the
mobile layout conventions of ``web_responsive``.

Use **Dark Mode** in the user menu to switch appearances. Under profile
preferences, **Use System Theme** follows the device's appearance. An explicit
switch disables system following. Preferences are stored per user.

In menu search, **Up/Down** highlights results and **Enter** opens the selected
menu. Typing resets the selection; keyboard navigation keeps the search input
focused and scrolls the highlighted result into view.

Migration from web_dark_mode
----------------------------

Install ``altinkaya_theme`` without running the legacy addon's uninstall. Its
installation hook transfers the existing field and preference-view external
identifiers and marks ``web_dark_mode`` uninstalled without dropping user
preference columns. It refuses pending module operations, dependent installed
addons and conflicting external identifiers instead of silently overwriting
them. After confirming that ``altinkaya_theme`` is installed and
``web_dark_mode`` is uninstalled, remove the old addon directory and its
``addons/web_dark_mode`` link. Restart Odoo so only the new theme's assets load.

The two stored preference fields retain their original technical names:
``dark_mode`` and ``dark_mode_device_dependent``. New databases can install
this addon directly; the legacy addon is not a dependency.

Credits
-------

The original dark-mode preference integration is derived from the AGPL-3
``web_dark_mode`` addon by Florian Kantelberg / initOS GmbH and OCA.
Theme design and appearance handling: Altinkaya Enclosures.
