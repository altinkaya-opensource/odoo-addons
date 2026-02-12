-- neutralize API credentials
UPDATE trendyol_backend
   SET api_key = 'NEUTRALIZED',
       api_secret = 'NEUTRALIZED',
       seller_id = '000000',
       webhook_api_key = 'NEUTRALIZED',
       webhook_id = NULL,
       webhook_url = NULL,
       environment = 'stage';

-- deactivate all trendyol cron jobs
UPDATE ir_cron
   SET active = false
 WHERE id IN (
       SELECT res_id
         FROM ir_model_data
        WHERE model = 'ir.cron'
          AND module = 'trendyol_integration'
);
