def migrate(cr, version):
    """Store FedEx shipping costs without the list price.

    carrier_shipping_cost held totalBaseCharge, the list price before the
    account discount. Recompute it as the billed total without VAT.
    """
    if not version:
        return

    cr.execute(
        """
        UPDATE stock_picking sp
        SET carrier_shipping_cost =
            sp.carrier_shipping_total - COALESCE(sp.carrier_shipping_vat, 0)
        FROM delivery_carrier dc
        WHERE dc.id = sp.carrier_id
          AND dc.delivery_type = 'fedex'
          AND sp.carrier_shipping_total > 0
        """
    )
