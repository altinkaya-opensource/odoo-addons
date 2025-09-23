-- disable iyzico payment provider
-- TODO
UPDATE payment_provider
   SET iyzico_api_key = NULL,
       iyzico_secret_key = NULL
