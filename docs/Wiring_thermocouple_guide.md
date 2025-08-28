# Phorest Pipeline: Wiring with a Raspberry Pi

This document provides an overview of how to connect the DS18B20 digital thermocouple to the Raspberry Pi.

## Components

* Raspberry Pi
* DS18B20 Temperature Sensor
* 4.7k Ohm Resistor
* Breadboard and jumper wires (optionally connect components in-line with Raspberry Pi GPIO connector)

## Connection steps

1.  Connect the DS18B20's power line (red wire) to the Pi's 3.3V pin.
2.  Connect the DS18B20's ground line (black wire) to the Pi's ground pin.
3.  Connect the DS18B20's data line (yellow wire) to a GPIO pin on the Pi. The default is GPIO4, but you can choose another pin.
4.  Place the 4.7k Ohm resistor between the 3.3V line and the data line either use an external breadboard or connect in-line. This connects the data line to the 3.3V rail.
5.  Enable the 1-Wire interface in the Raspberry Pi's software using the raspi-config tool. 