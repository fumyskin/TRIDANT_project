# TRIDANT_project
Repository for microcontroller programming  repo of experimental setup of the multi-function Dielectric Resonator Antenna

- Vittoria : this is a repo check

Board testing code structure:
ESP32_BLE -> Python BLE bridge -> Python web server
    |           |        |           |    
    \--- BLE ---/        \--- ws  ---/    
The two channels are BLE and websocket, the server serves a local https page (cert and key generated with git bash cause of windows11)
To start it activate the virtual environment in two terminals, start both python scripts and open the localhost webpage (should be https://localhost:8443/)