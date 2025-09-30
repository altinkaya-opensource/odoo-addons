UPDATE bulutsantralim_connector
SET api_key = 'dummy';

UPDATE crm_phonecall
SET verimor_call_uuid = NULL, verimor_recording_url = NULL, verimor_call_data = NULL;

UPDATE res_partner
SET internal_number = NULL;
