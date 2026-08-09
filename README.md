# heater40C

A MicroPython-based electronic project using high accuracy chainable temperature sensors

## Equipment

#![The assembled equipment](ct3PZEMboxedView.jpg)

The assembled project showing the ESP32, PZEM module.

## Project Overview

This project uses an ESP32 to obtain temperature data that is transmitted to other systems via MQTT.

## Main Components

- NodeMcu ESP32 WROOM-32 Type C CH340C Development Board Dual Core WiFi Bluetooth


## Software

- Written in MicroPython
- heater40C.py is main program needing
- other shared modules with filenames starting with mod

## Circuit
![KiCAD Circuit](20250817kcHeaterschematic.jpg)  
20250817kcHeaterschematic.jpg

![DS18B20 pinout](DS18B20pinout.jpg)  
DS18B20pinout.jpg

## How It Works

Periodically 

## Installation

The ESP32 was programmed using Thonny on a Linux Xubuntu system. Thonny is available for Windows, macOS and Linux, so the same MicroPython development environment can be used regardless of the computer's operating system.
Alternatives exist but Thonny as the simplest cross-platform choice.

## Configuration

Some modules need setting up. A header in each module gives notes on setup.

1) **modWiFi**  
wifi_entries.dat holds WiFi connections credentials. For a fixed system just one line Entry is needed. The format is like:
SSID::PASSWORD::Region
SSID and PASSWORD can contain a large range of characters including a space character.
Region is a single uppercase letter. L=London time and P=Paris time 
The file is then saved in ESP32 flash.

2) **modMQTpub**  
mqcons.py here is a template to be filled in with data from an MQTT server such as HiveMQ, and saved in ESP32 flash.

3) **modDateTime**  
Write the daylight saving string defined at the start of the module
into a file named "dst.rule" and save in ESP32 flash.

## Test Setup

#![Test Rig](calibTestSetup.jpg) 

## Power Supply

![Volts Amps Monitor](heater40CpowerAmmeterMonitor.jpg)  
heater40CpowerAmmeterMonitor.jpg

![Ammeter Circuit](ammeterCircuit.jpg)  
ammeterCircuit.jpg 

## Version History

Each MicroPython file has Filename and Version in the first two lines.
