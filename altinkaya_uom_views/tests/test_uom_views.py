from ast import literal_eval

from lxml import etree

from odoo.tests.common import TransactionCase, tagged

MO_FORM = "mrp.mrp_production_form_view"
PICKING_FORM = "stock.view_picking_form"
SALE_FORM = "sale.view_order_form"
MOVE_LINE_TREE = "stock.view_stock_move_line_detailed_operation_tree"
QUANT_COUNT_TREE = "stock.view_stock_quant_tree_inventory_editable"
RAW_TREE = "//field[@name='move_raw_ids']/tree/field[@name='%s']"
PICKING_TREE = "//field[@name='move_ids_without_package']/tree/field[@name='%s']"
SALE_TREE = "//field[@name='order_line']/tree/field[@name='%s']"
BOM_FORM = "mrp.mrp_bom_form_view"
BOM_TREE = "//field[@name='bom_line_ids']/tree/field[@name='%s']"
ROOT_TREE = "//tree/field[@name='%s']"
COUNTED = "counted_quantity_widget"
FORECAST = "forecast_widget"

# view, expression, widget, unit field
QUANTITY_NODES = [
    (MO_FORM, RAW_TREE % "product_uom_qty", "mrp_should_consume", "product_uom"),
    (MO_FORM, RAW_TREE % "quantity_done", "mrp_consumed", "product_uom"),
    (MO_FORM, RAW_TREE % "forecast_availability", "uom", "product_uom"),
    (
        PICKING_FORM,
        PICKING_TREE % "forecast_availability",
        "forecast_widget",
        "product_uom",
    ),
    (PICKING_FORM, PICKING_TREE % "quantity_done", "uom", "product_uom"),
    (MOVE_LINE_TREE, ROOT_TREE % "qty_done", "uom", "product_uom_id"),
    (QUANT_COUNT_TREE, ROOT_TREE % "inventory_quantity", COUNTED, "product_uom_id"),
    (SALE_FORM, SALE_TREE % "product_uom_qty", "uom", "product_uom"),
    (BOM_FORM, BOM_TREE % "product_qty", "uom", "product_uom_id"),
]


@tagged("post_install", "-at_install")
class TestUomViews(TransactionCase):
    def test_quantity_nodes(self):
        """Each quantity keeps its widget and names its own unit."""
        for view_xmlid, expression, widget, uom_field in QUANTITY_NODES:
            with self.subTest(view=view_xmlid, expression=expression):
                arch = etree.fromstring(self.env.ref(view_xmlid).get_combined_arch())
                node = arch.xpath(expression)[0]
                self.assertEqual(node.get("widget"), widget)
                self.assertEqual(
                    literal_eval(node.get("options"))["uom_field"], uom_field
                )

    def test_invoice_lines_are_left_alone(self):
        """Invoice quantities keep the plain float display."""
        view = self.env.ref("account.view_move_form")
        arch = etree.fromstring(view.get_combined_arch())
        nodes = arch.xpath("//field[@name='invoice_line_ids']//field[@name='quantity']")
        self.assertTrue(nodes)
        self.assertFalse([node for node in nodes if node.get("widget") == "uom"])
