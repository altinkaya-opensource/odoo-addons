def migrate(cr, version):
    """Store the dummy remainder threshold as a percent.

    The threshold used to be read as a ratio, so carriers set to 0.5 meant
    50%. A value below 1 was a ratio; values from 1 up already are percents.
    """
    if not version:
        return

    cr.execute(
        """
        UPDATE delivery_carrier
        SET dummy_remainder_threshold_percent =
            dummy_remainder_threshold_percent * 100
        WHERE dummy_remainder_threshold_percent > 0
          AND dummy_remainder_threshold_percent < 1
        """
    )
