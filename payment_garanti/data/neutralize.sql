UPDATE payment_provider
SET garanti_merchant_id = NULL, garanti_terminal_id = NULL, garanti_prov_user = NULL, garanti_prov_password = NULL, garanti_store_key = NULL;

UPDATE payment_transaction
SET garanti_secure3d_hash = NULL, garanti_xid = NULL;
