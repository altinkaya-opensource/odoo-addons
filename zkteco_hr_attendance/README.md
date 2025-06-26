# ZKTeco HR Attendance

Integration module for ZKTeco biometric attendance devices with Odoo HR Attendance.

## What is this for?

Automatically synchronize employee attendance data from ZKTeco devices to Odoo, eliminating manual data entry.

## Dependencies

- **Odoo modules**: `hr`, `hr_attendance`
- **Python**: `pyzk` library

## Installation

1. Install Python dependency:
   ```bash
   pip install pyzk
   ```

2. Install the module through Odoo Apps menu

## How to use

1. **Configure Device**: Go to HR > Configuration > ZKTeco Devices, add your device IP and port
2. **Test Connection**: Click "Test Connection" button
3. **Map Employees**: Set ZKTeco User ID in employee records
4. **Sync Attendance**: Click "Get Attendance" to fetch records from device

## Contributors

- **Ahmet Yiğit Budak** - [@yibudak](https://github.com/yibudak)
- **Altinkaya Enclosures** - [altinkaya-opensource](https://github.com/altinkaya-opensource/odoo-addons)

## License

LGPL-3
