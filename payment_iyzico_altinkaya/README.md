# Payment Provider: iyzico

This module integrates iyzico payment gateway with Odoo, providing secure online payment
processing for credit card transactions.

## Features

- **Secure Payment Processing**: Integrates with iyzico's secure payment infrastructure
- **Installment Support**: Allows customers to pay in installments (available for
  Turkish customers)
- **3D Secure Authentication**: Supports 3D Secure for enhanced security
- **Multi-currency Support**: Handles different currencies with automatic conversion
- **Real-time Installment Calculation**: Shows available installment options based on
  card number

## Installation

1. Install the module in your Odoo instance
2. Configure the payment provider settings
3. Obtain API credentials from iyzico

## Configuration

### Payment Provider Setup

1. Go to **Accounting > Payments > Payment Providers**
2. Create a new payment provider with code `iyzico_altinkaya`
3. Configure the following settings:

   - **API Key**: Your iyzico API key
   - **Secret Key**: Your iyzico secret key
   - **State**: Set to "Enabled" for production
   - **Enable Installments**: Check to allow installment payments
   - **3DS Threshold Amount**: Set minimum amount for 3D Secure (0 = always require 3D
     Secure)

### Supported Currencies

The module automatically handles currency conversion for Turkish customers when the
transaction currency differs from TRY.

## Usage

### For Customers

1. During checkout, select "iyzico" as payment method
2. Enter credit card details
3. For Turkish customers with installment-enabled cards, installment options will be
   displayed
4. Complete the payment

### For Administrators

- Monitor transactions in **Accounting > Payments > Payment Transactions**
- View payment provider logs for troubleshooting
- Configure 3D Secure thresholds and installment settings

## Technical Details

### Dependencies

- `account_payment`
- `payment`
- `requests` (external Python library)

### API Integration

The module communicates with iyzico's REST API for:

- Payment processing
- Installment information retrieval
- 3D Secure authentication

### Security

- All sensitive data is encrypted
- PCI DSS compliant payment processing
- Secure token-based authentication

## Support

For support and issues:

- GitHub Issues: [odoo-addons](https://github.com/altinkaya-opensource/odoo-addons)

## License

This module is licensed under LGPL-3.

## Authors

- Ahmet Yiğit Budak
- Altinkaya Enclosures

## Changelog

### 16.0.0.1.0

- Initial release
- Support for iyzico payment gateway
- Installment options for Turkish customers
- 3D Secure authentication
- Multi-currency support
