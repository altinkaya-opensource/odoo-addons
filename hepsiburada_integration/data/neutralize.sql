-- neutralize API and webhook credentials
UPDATE hepsiburada_backend
   SET merchant_id = '00000000-0000-0000-0000-000000000000',
       api_username = 'NEUTRALIZED',
       api_password = 'NEUTRALIZED',
       webhook_enabled = false,
       webhook_username = NULL,
       webhook_password = NULL,
       environment = 'stage';

-- deactivate all hepsiburada cron jobs
UPDATE ir_cron
   SET active = false
 WHERE id IN (
       SELECT res_id
         FROM ir_model_data
        WHERE model = 'ir.cron'
          AND module = 'hepsiburada_integration'
);
