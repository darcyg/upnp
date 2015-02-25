#UPNP library

### UPNP library for use in smarthome
(C) Michael Würtenberger 2015
 
v 0.1

### Features
- ssdp discovery implemented. finds (hopefully all ssdp adressable devices)
    - timing and ST could be given as parameters
- scans on top of ssdp discovers all found hosts for upnp devices and their services
- offers as dict with all the informations for configuration 