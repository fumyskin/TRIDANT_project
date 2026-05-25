#include <stdio.h>
#include <esp_log.h>
#include <esp_adc/adc_oneshot.h>
#include <esp_adc/adc_cali.h>
#include <esp_adc/adc_cali_scheme.h>

#define EXAMPLE_ADC_UNIT    ADC_UNIT_1
#define EXAMPLE_ADC_CHANNEL ADC_CHANNEL_4   
#define EXAMPLE_ADC_ATTEN   ADC_ATTEN_DB_11

void app_main(void){
  // adc unit initialization
  adc_oneshot_unit_handle_t adc_handle;
  adc_oneshot_unit_init_cfg_t init_config = {
    .unit_id = EXAMPLE_ADC_UNIT,
  };
  ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config, &adc_handle));

  // adc channel configuration
  adc_oneshot_chan_cfg_t config = {
    
  }
}