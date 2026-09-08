Altinkaya Theme
===============

A shared backend design for Odoo 16 Community with modern light and dark
palettes. Forms, navigation, buttons, notebooks, chatter, badges and alerts
use the same component rules in both appearances. A searchable application
launcher and a mobile section menu replace web_responsive. Uninstall
web_responsive before installing or upgrading this theme. Compatible with
``web_company_color`` and ``web_theme_classic``. Website and report bundles
do not receive the backend component styles.

Use **Dark Mode** in the user menu to switch appearances. Under profile
preferences, **Use System Theme** follows the device's appearance. An explicit
switch disables system following. Preferences are stored per user.

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
