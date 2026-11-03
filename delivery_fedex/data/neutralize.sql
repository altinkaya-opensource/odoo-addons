update delivery_carrier
SET fedex_client_id = NULL, fedex_client_secret = NULL, fedex_account_number = NULL, fedex_tracking_client_id = NULL, fedex_tracking_client_secret = NULL;
DELETE FROM ir_logging WHERE func IN ('fedex_auth_request', 'fedex_auth_response');
