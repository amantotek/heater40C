gsFilNom = "heater40C.py" #Written in MicroPython for ESP32 WROOM
gsVEERSN = gsFilNom + " V028" # Remove gfAmbTemp < 20.0 degC clause that turned off htr above 20degC
glFixdIP = "192.168.0.74"

# Supports:
#   http://192.168.0.74/rd - Read two DS18B20 sensors (ambient, heater). Used by halsg.py
#   http://192.168.0.74/rv - Version and IP
#   http://192.168.0.74/rn - Turn heater ON
#   http://192.168.0.74/rf - Turn heater OFF
#   http://192.168.0.74/rh - Turn heater ON for MAXHEATON (failsafe). Used by halsg.py

# Test before OTA on laptop terminal: 
# cd /home/andymc/fotmus/malwebDesign/projects/heater40C/;python3 -m py_compile heater40CV022.py
# cd /home/andymc/fotmus/malwebDesign/projects/ESP32/;python3 -m py_compile modMQTpubV022.py

#Example of Using OTA in Xubuntu terminal
#----------------------------------------
# cd ~/fotmus/malwebDesign/projects/heater40C   (Project folder)
# ls -alt *.py
# cp heater40CV0??.py heater40C.py   (Use latest version)
# curl http://192.168.0.74/rv    (check version on the ESP32)
# curl -X POST --data-binary @heater40C.py http://192.168.0.74/pub   (Upload new version)
# curl http://192.168.0.74/rv    (check version has changed)
# curl -X POST --data-binary @modMQTpub.py http://192.168.0.74/pub/modMQTpub.py

import uasyncio
from machine import Pin, reset
import onewire, ds18x20, time, gc

#Ours
import modDateTime #V010
import modKeepAlive #V002
import modMQTpub #V023
import modOTAserver #V003
from modWiFi import wifiConnect,start_config_portal #V017
import mqcons

MAXHEATON = 16 #10 gave ~15.08 to ~15.41 sec actual variable. So 17 shud giv ~25s. halsg.py polling ~26s
MAXDEGC = 39.0  # Maximum DegC of Heater
bgHeatDemanded = False  # Global heat demand flag (renamed from bgHeaterOn)
igHeat = 0
igSendCt = 0

bluled = Pin(2, Pin.OUT)
heater_pin = Pin(23, Pin.OUT)
heater_pin.value(0)

gfAmbTemp = None
gfHeatTemp = None

gsTopicSub = "op/m2e" #Check for manual update being pressed see halEsp32t.py
ECYGETHALDATA = "GETHALINF"
giLastMinute = -1

def dbpriint(sTcv):
    #print(sTcv) #Comment out for production
    pass
    
async def heapTask():
    await uasyncio.sleep(5)
    while True:
        gc.collect() # Optional but recommended so seeing the amount of genuinely free memory after a collection
        dbpriint(f"Free RAM:{gc.mem_free()}")
        await uasyncio.sleep(600) #secs (yield for 10 mins)

def fnUpdatePressed():
    #dbpriint("fn Update Pressed ")
    _publishH4CPayload()
        
mqttPub = modMQTpub.MQTTPublisher(
     sDeviceLabel=gsVEERSN,
     sBrokerHost=mqcons.sBrokerHost,
     iBrokerPort=mqcons.iBrokerPort,
     sMqttUser=mqcons.sMqttUser,
     sMqttPassword=mqcons.sMqttPassword,
     sTopicPub="op/htr",
     sTopicSub=gsTopicSub,
     sExpectedSubMsg=ECYGETHALDATA,
     fnUpdateCallback=fnUpdatePressed,
     sClientId=None
    )

def _publishH4CPayload():
    global gfAmbTemp, gfHeatTemp
    try:
        if gfAmbTemp is None:
            return False
        if gfHeatTemp is None:
            return False
        if mqttPub is None:
            return False
        sHHMM = "{:02}:{:02}{}".format(
            giNowHour,
            giNowMinute,
            gcDSTsuffixUBG
        )
        dPayload = {
            "a": round(gfAmbTemp, 1),
            "h": round(gfHeatTemp, 1),
            "on": heater_pin.value() == 1,
            "t": sHHMM
        }
        bOK = mqttPub.fnMQTTPublish(dPayload)
        if bOK  == False:
            if gbDebug: dbpriint("DBH4C TX FAILED")
        return bOK
    except Exception as e:
        if gbDebug: dbpriint(f"DBH4C Publish error:{e}")
        return False

# ---------------------------
# Startup LED blink this is for testing/development to show a restart has been made
def flash_startup():
    for _ in range(6):
        bluled.on()
        time.sleep(0.2)
        bluled.off()
        time.sleep(0.2)
flash_startup()

# ---------------------------
# DS18B20 setup
sensor_rom_map = {
    'heeter': '28f74122000000ba',
    'ambbient':  '28d2a123000000b2',
}
ow = onewire.OneWire(Pin(22))
gvds = ds18x20.DS18X20(ow)
gRomA = bytearray.fromhex(sensor_rom_map['ambbient'])
gRomH = bytearray.fromhex(sensor_rom_map['heeter'])

def degCsensers():
  roms = gvds.scan()
  dbpriint(f"Found {len(roms)} DS18B20 sensor(s)")
  for rom in roms:
    dbpriint(f"ROM:{rom.hex()}")

async def sensor_task():
    #If the OneWire bus glitches, convert_temp() can throw an exception.
    #If that escapes the task the coroutine dies permanently.
    global gfAmbTemp, gfHeatTemp
    lastScan = time.ticks_ms()
    while True:
        try:
            gvds.convert_temp() # start conversion
        except Exception as e:
            dbpriint(f"convert error:{e}") #never let an exception escape the loop
            await uasyncio.sleep(2)
            continue        
        await uasyncio.sleep_ms(750)
        #If a sensor disconnects don't keep old value.
        try:
            gfAmbTemp = gvds.read_temp(gRomA)
        except:
            gfAmbTemp = None
        try:
            gfHeatTemp = gvds.read_temp(gRomH)
        except:
            gfHeatTemp = None
        await uasyncio.sleep_ms(20) #Give the event loop a second yield point
        #Periodic rescan to recover if OneWire bus locks up after electrical noise
        if time.ticks_diff(time.ticks_ms(), lastScan) > 300000:
            gvds.scan() #every 5 mins
            lastScan = time.ticks_ms()

# ---------------------------
# Blue LED control (all LED actions centralised here)
led_alt_state = False
last_b_time = 0
last_a_time = 0
blip_active = False
blip_start = 0

# ---------------------------
# Async LED manager (runs independently of checkState)
async def led_manager():
    global led_alt_state, last_a_time
    global blip_active, blip_start, last_b_time, blip_base_on
    while True:
        now = time.ticks_ms()
        # Handle blip (non-blocking, fires every 3s, LED inverted from base for 100ms)
        if blip_active and time.ticks_diff(now, blip_start) > 100:
            bluled.value(1 if blip_base_on else 0)  # restore base state
            blip_active = False
        # Handle alternate mode (toggles every 500ms)
        if led_alt_state is not None and time.ticks_diff(now, last_a_time) >= 500:
            led_alt_state = not led_alt_state
            bluled.value(1 if led_alt_state else 0)
            last_a_time = now
        await uasyncio.sleep_ms(50)  # check LEDs frequently without hogging CPU

def bluuLED(cMode):
    """Set LED mode: f=off, n=on (reverse blip), b=blip (idle), a=alternate"""
    global led_alt_state, blip_active, blip_start, last_b_time, blip_base_on
    if cMode == 'f':  # Force off
        bluled.off()
        led_alt_state = None
        blip_active = False

    elif cMode == 'n':  # Reverse blip (LED on, blips off)
        blip_base_on = True
        bluled.on()
        led_alt_state = None
        # trigger first blip immediately if not active
        if not blip_active and time.ticks_diff(time.ticks_ms(), last_b_time) > 3000:
            bluled.value(0)  # invert base
            blip_active = True
            blip_start = time.ticks_ms()
            last_b_time = blip_start

    elif cMode == 'b':  # Normal blip (LED off, blips on)
        blip_base_on = False
        bluled.off()
        led_alt_state = None
        if not blip_active and time.ticks_diff(time.ticks_ms(), last_b_time) > 3000:
            bluled.value(1)  # invert base
            blip_active = True
            blip_start = time.ticks_ms()
            last_b_time = blip_start

    elif cMode == 'a':  # Switch to alternate mode
        led_alt_state = False
        last_a_time = time.ticks_ms()
        
def nextSendCt():
    #Counter to show response has changed
    global igSendCt
    igSendCt += 1
    if igSendCt > 99:
        igSendCt = 0
    return f"({igSendCt:02d})"        

# ---------------------------
# Determine Heater on/off state every 1s
async def checkState():
    global igHeat, bgHeatDemanded
    #TENMINSINSECS = 600 #secs (10 minutes)
    #iRamCountdown = TENMINSINSECS
    await uasyncio.sleep(2) #Anti heater control task running before the first temperature reading.
    while True:
        #iRamCountdown -= 1
        #if iRamCountdown <= 0:
        #    gc.collect() # Optional but recommended so seeing the amount of genuinely free memory after a collection
        #    dbpriint("Free RAM:", gc.mem_free()) #Dropping figure indicates memory leak
        #    iRamCountdown = TENMINSINSECS
        
        if igHeat > 0:
            igHeat -= 1
        if igHeat == 0:
            bgHeatDemanded = False
        if not bgHeatDemanded:
            heater_pin.value(0)  # No power
            bluuLED('b')        # Idle: blip occasionally
        else:
            #Below changed as Daikin reported outside degC as 19 (putting htr off so HP on) and we measure gfAmbTemp as 22.8
            #if gfHeatTemp is not None and gfAmbTemp is not None and gfHeatTemp < MAXDEGC and gfAmbTemp < 20.0:
            if gfHeatTemp is not None and gfAmbTemp is not None and gfHeatTemp < MAXDEGC:
                heater_pin.value(1)
                bluuLED('a')    # Heating: alternate LED
            else:
                heater_pin.value(0)
                bluuLED('n')    # Max temp: LED on
        await uasyncio.sleep(1)
    
#Deal with requests from the user
def fnrv():
    return gsVEERSN

def fnreset():
    reset()  # reboot device

def fnrd():
    #Used by halsg.py see URL_RD
    if gfAmbTemp is None or gfHeatTemp is None:
        return "Temps not ready"
    return f"Ambient {gfAmbTemp:.1f} degC, Heater {gfHeatTemp:.1f} degC " + nextSendCt()

def fnrh():
    #Used by halsg.py see URL_RH
    global bgHeatDemanded, igHeat
    bgHeatDemanded = True
    igHeat = MAXHEATON
    return "Heater ON timed " + nextSendCt()
    
def fnrn():
    global bgHeatDemanded, igHeat
    bgHeatDemanded = True
    igHeat = 999999
    return "Heater ON"

def fnrf():
    global bgHeatDemanded, igHeat
    bgHeatDemanded = False
    igHeat = 0
    return "Heater OFF"

# ---------------------------
# Main entry
async def main():
    global giLastMinute, giNowHour, giNowMinute, gcDSTsuffixUBG
    ##global glFixdIP, mqttPub, gsVEERSN, gsFilNom
    # -------------------------------
    # 1) WiFi FIRST
    # -------------------------------
    cRegion = wifiConnect(fixed_ip=glFixdIP) # returns 'L', 'P', or None
    if cRegion is None:
        dbpriint("Starting Wi-Fi config portal")
        start_config_portal() #This will reboot and hopefully use new wifi setup
    else:    
        dbpriint(f"WiFI done {cRegion}")

    # -------------------------------
    # 2) MQTT Setup
    # -------------------------------
    dbpriint("DB Starting MQTT setup")
    mqttPub.fnMQTTConnectAndSubscribe()
    if mqttPub.bConn:
        dbpriint("DB MQTT connected")
    else:
        dbpriint("DB MQTT NOT connected")
        
    # -------------------------------
    # 3) OTA server setup
    # -------------------------------
    commandHandlers={
        "/reset": fnreset,
        "/rd": fnrd,
        "/rv": fnrv,
        "/rh": fnrh, 
        "/rn": fnrn,
        "/rf": fnrf
    }
    modOTAserver.startHttpServer(fixedIP=glFixdIP,sComands=commandHandlers,sVeersion=gsVEERSN,sFileToChnge=gsFilNom)

    # -------------------------------
    # 4) Keep Alive
    # -------------------------------    
    modKeepAlive.fnStart()
    
    # -------------------------------
    #  5) Date/Time/DST setup
    # -------------------------------
    sTgudq = modDateTime.fnInitializeModule(cRegion)
    dbpriint(sTgudq) #Initially
    dbpriint(modDateTime.sGetLocalTimeString()) #Initially
    #Do below once
    sCmd="diUTC0;DST+1;M3.lastSun@01:00UTC-M10.lastSun@01:00UTC"
    modDateTime.handleDstCommand(sCmd)    

    # -------------------------------
    # 6) Core tasks
    # -------------------------------
    uasyncio.create_task(modKeepAlive.taskKeepAlive())
    uasyncio.create_task(checkState()) # Replaces heater_control_loop
    uasyncio.create_task(led_manager())
    uasyncio.create_task(sensor_task())
    uasyncio.create_task(heapTask())
    dbpriint("Publish to MQTT setup looking good")
    degCsensers()
    dbpriint("All main systems setup")

    # ----------------------------------------
    # 6) Wait for Activity
    # ----------------------------------------
    while True:
        modKeepAlive.fnAlive("main")
            
        # 1) Ensure we have a client & Check subscription to MQTT server
        try:
            if not mqttPub.bConn:
                dbpriint("MQTT reconnecting")
                mqttPub.fnMQTTConnectAndSubscribe()
            else:
                mqttPub.fnMQTTCheckSubscriptions()
        except Exception as e:
            dbpriint(f"MQTT error:{e}")
            mqttPub.bConn = False                      

        # 2) Now safe to publish heater data to MQTT cloud 
        try:
            year, month, day, giNowHour, giNowMinute, second, iDayOfWeek, gcDSTsuffixUBG = modDateTime.tzGetLocalDateTime()
            bDoRead = False            
            if giNowMinute != giLastMinute:
                giLastMinute = giNowMinute
                bDoRead = True
            if bDoRead == True:
                _publishH4CPayload()
        except Exception as e:
            #record_error(str(e))
            dbpriint(f"Pub err:{e}")
        await uasyncio.sleep(1)
        
try:
    uasyncio.run(main())
except Exception as e:
    dbpriint(f"Fatal error:{e}")
    reset()
# --- end ---
