# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "ZKTeco HR Attendance",
    "summary": "ZKTeco Attendance Device Integration",
    "version": "16.0.1.0.0",
    "author": "Ahmet Yiğit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "LGPL-3",
    "category": "Tools",
    "depends": ["hr", "hr_attendance"],
    "external_dependencies": {"python": ["pyzk"]},
    "data": [
        "data/cron.xml",
        "security/ir.model.access.csv",
        "views/hr_employee_view.xml",
        "views/hr_attendance_view.xml",
        "views/zkteco_device_view.xml",
    ],
    "installable": True,
}
