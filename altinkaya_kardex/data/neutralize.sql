-- Point every machine away from the JMIF gateway, which moves the real
-- vertical lifts. JmifRequest only sends basic auth when jmif_user is set,
-- so wiping the credentials alone would still let a copy move trays.
-- host is NOT NULL, hence a placeholder.
UPDATE stock_kardex
   SET host = 'localhost',
       jmif_user = NULL,
       jmif_password = NULL;
