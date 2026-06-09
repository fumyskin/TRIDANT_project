// // protocol that is supposed to read from adc data and processes it
// #include <stdio.h>
// #include <esp_log.h>
// #include <freertos/FreeRTOS.h>
// #include <freertos/task.h>
// #include <esp_adc/adc_oneshot.h>
// #include <esp_adc/adc_cali.h>
// #include <esp_adc/adc_cali_scheme.h>

// #define EXAMPLE_ADC_UNIT    ADC_UNIT_1
// #define EXAMPLE_ADC_CHANNEL ADC_CHANNEL_1  
// #define EXAMPLE_ADC_ATTEN   ADC_ATTEN_DB_12

// static const char *TAG = "LDR_ADC";
// static bool adc_calibration_init(adc_unit_t unit, 
//                                 adc_channel_t channel, 
//                                 adc_atten_t atten,
//                                 adc_cali_handle_t *out_handle)
// {
//     adc_cali_handle_t handle = NULL;
//     esp_err_t ret = ESP_FAIL;

// #if ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
//     adc_cali_curve_fitting_config_t cali_config = {
//         .unit_id = unit,
//         .chan = channel,
//         .atten = atten,
//         .bitwidth = ADC_BITWIDTH_DEFAULT,
//     };
//     ret = adc_cali_create_scheme_curve_fitting(&cali_config, &handle);
// #elif ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED
//     adc_cali_line_fitting_config_t cali_config = {
//         .unit_id = unit,
//         .atten = atten,
//         .bitwidth = ADC_BITWIDTH_DEFAULT,
//     };
//     ret = adc_cali_create_scheme_line_fitting(&cali_config, &handle);
// #endif

//     *out_handle = handle;
//     if (ret == ESP_OK) {
//         ESP_LOGI(TAG, "Calibration scheme initialized");
//         return true;
//     }
//     ESP_LOGW(TAG, "Calibration not available; raw values only");
//     return false;
// }

// void app_main(void){

//   // adc unit initialization
//   adc_oneshot_unit_handle_t adc_handle;
//   adc_oneshot_unit_init_cfg_t init_config = {
//     .unit_id = EXAMPLE_ADC_UNIT,
//   };
//   ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config, &adc_handle));

//   // adc channel configuration
//   adc_oneshot_chan_cfg_t config = {
//     .atten = EXAMPLE_ADC_ATTEN,
//     .bitwidth = ADC_BITWIDTH_DEFAULT,
//   };
//   ESP_ERROR_CHECK(adc_oneshot_config_channel(adc_handle, EXAMPLE_ADC_CHANNEL, &config));

//   // calibration
//   adc_cali_handle_t cali_handle = NULL;
//   bool calibrated = adc_calibration_init(EXAMPLE_ADC_UNIT, EXAMPLE_ADC_CHANNEL,
//                                             EXAMPLE_ADC_ATTEN, &cali_handle);
//   // loop
//   while(1){
//     int raw = 0;
//     ESP_ERROR_CHECK(adc_oneshot_read(adc_handle, EXAMPLE_ADC_CHANNEL, &raw));

//     if(calibrated){
//         int voltage_mv = 0;
//         ESP_ERROR_CHECK(adc_cali_raw_to_voltage(cali_handle, raw, &voltage_mv));
//         ESP_LOGI(TAG, "LADR raw=%d, voltage=%d mV", raw, voltage_mv);
//     }else{
//         ESP_LOGI(TAG, "LADR raw=%d (uncalibrated)", raw);
//     }

//     vTaskDelay(pdMS_TO_TICKS(500));
//   }
// }