UPDATE payment_provider
SET moka_dealer_code = NULL, moka_username = NULL, moka_password = NULL;

UPDATE payment_transaction
SET moka_tx_code = NULL, moka_success_hash = NULL, moka_fail_hash = NULL;
