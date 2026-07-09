# PARAMETERS FOR CORRECT USAGE OF GUI ON GNSS AND V2X

# FINDING R_MIN, R_MAX
 1) GNSS: run `python capture_ble.py --dbm --band GNSS`, perform a complete azimuth sweep and check the `peak` value : that's your `R_MAX` to be inserted in the `tridant_gui.py`
 2) V2X: run `python capture_ble.py --dbm --band V2X`, perform a perform a complete azimuth sweep and check the `peak` value : that's your `R_MAX` to be inserted in the `tridant_gui.py`

## GNSS
`capture_ble.py`:
 1) set `DEFAULT_PROFILE` to `"GNSS_1G575"`

`tridant_gui.py`:
 1) set `PROFILE` to `"GNSS_1G575"`
 2) set `R_MAX = -5.5`  and `R_MIN = -60.0`
 3) set proper GNSS calibration based on the LPD model used:
    if ADP317: slope = -22 mv/db; intercept = 315 mv
    if ADP318: 

## V2X
`capture_ble.py`:
 1) set `DEFAULT_PROFILE` to `"V2X_5G9"`

`tridant_gui.py`:
 1) set `PROFILE` to `"V2X_5G9"`
 2) set `R_MAX = `  and `R_MIN = -60.0` 
 3) set proper GNSS calibration based on the LPD model used:
    ADP317: slope = -22 mv/db; intercept = 352 mv
    ADP318: 