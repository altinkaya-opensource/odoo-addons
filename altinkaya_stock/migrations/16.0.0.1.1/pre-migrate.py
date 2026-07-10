# License LGPL-3
def migrate(cr, version):
    """stock.location.comment: Html -> Char(size=64).

    Runs before the ORM converts the column from ``text`` to ``varchar(64)``.
    Strips HTML tags and a few common entities, trims, and truncates to 64 chars
    so existing notes don't carry raw ``<p>`` markup (and the shrink is lossless
    from the user's point of view for the short notes this field is meant to hold).
    """
    if not version:
        return
    cr.execute(
        r"""
        UPDATE stock_location
        SET comment = LEFT(
            BTRIM(
                regexp_replace(
                    replace(replace(comment, '&nbsp;', ' '), '&amp;', '&'),
                    '<[^>]+>', '', 'g'
                )
            ),
            64
        )
        WHERE comment IS NOT NULL AND comment <> ''
        """
    )
