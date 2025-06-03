# Odoo Ideasoft XML Export Module

This Odoo module simplifies exporting product data from Odoo to Ideasoft XML format. It
provides a configurable backend to manage export settings and generates a public XML
endpoint for easy integration.

## Keywords

Odoo, Ideasoft, XML Export, Data Integration, E-commerce, Odoo 16, Ideasoft Integration,
Product Export, Stock Export, Price Export

## Features

- **Configurable Exports**: Define product filters, brand, tax, currency, language, and
  stock locations.
- **Comprehensive Product Data**: Exports detailed product information including codes,
  names, categories, prices, stock levels, images, and descriptions.
- **Secure Public Endpoint**: Access generated XML via a unique, token-protected URL.
- **Automated Generation**: Supports scheduled XML generation via Odoo cron jobs.
- **Odoo 16 Compatible**.

## Installation

1.  Add this module to your Odoo `addons` path.
2.  Install dependencies: `sale`, `stock`, `product_logistics_uom`, `queue`.
3.  Restart Odoo and install the "Ideasoft XML Export" module from the Apps menu.

## Configuration and Usage

1.  Go to `Sales > Configuration > Ideasoft Backend` (or similar menu path).
2.  Create a new configuration record.
3.  Fill in the required fields: Name, Product Domain (Odoo domain for filtering
    products), Brand Name, Tax, Currency, Language, and Locations (for stock
    calculation).
4.  Click "Regenerate XML" to create the XML file.
5.  The "XML URL" field will provide the public link to your exported data.

## Bug Tracker

Bugs are tracked on GitHub Issues. Please check our
[issue tracker](https://github.com/altinkaya-opensource/odoo-addons/issues).

## Credits

### Authors

- Ahmet Yiğit Budak
- Altinkaya Enclosures

### Maintainers

- Altinkaya Enclosures

## License

This module is licensed under the LGPL-3.
