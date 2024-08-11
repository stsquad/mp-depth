import sys

# ruff: noqa: E402
sys.path.append("")

from machine import Pin,time_pulse_us,Timer
from time import sleep_us
from micropython import const

import asyncio
import aioble
import bluetooth

import random
import struct

# org.bluetooth.service.environmental_sensing
_ENV_SENSE_UUID = bluetooth.UUID(0x181A)
# org.bluetooth.characteristic.temperature
_ENV_SENSE_TEMP_UUID = bluetooth.UUID(0x2A6E)
# org.bluetooth.characteristic.gap.appearance.xml
_ADV_APPEARANCE_GENERIC_THERMOMETER = const(768)

# How frequently to send advertising beacons.
_ADV_INTERVAL_MS = 250_000

# Register GATT server.
depth_service = aioble.Service(_ENV_SENSE_UUID)

# org.bluetooth.characteristic.measurement_interval
_ENV_SENSE_MEASURE_INTERVAL = bluetooth.UUID(0x2A21)
pulse_val = aioble.Characteristic(
    depth_service, _ENV_SENSE_MEASURE_INTERVAL, read=True, notify=True
)
# Encode and update pulse (uint16, usec measured).
def update_pulse_val(pulse_in_us):
    val = struct.pack("<H", pulse_in_us)
    pulse_val.write(val, send_update=True)

_ENV_SENSE_LENGTH_METERS = bluetooth.UUID(0x2701)
dist_val = aioble.Characteristic(
    depth_service, _ENV_SENSE_LENGTH_METERS, read=True, notify=True
)

def update_distance(dist_in_cm):
    val = struct.pack("<f", dist_in_cm)
    dist_val.write(val, send_update=True)

# Register the service
aioble.register_services(depth_service)


# 4 bit display in LEDs
led0 = Pin(14, Pin.OUT)
led1 = Pin(15, Pin.OUT)
led2 = Pin(17, Pin.OUT)
led3 = Pin(16, Pin.OUT)

# Speed of sound in air m/s
# (dependant on pressure)
sofs = 343.0

echo = Pin(0, Pin.IN)
trig = Pin(1, Pin.OUT)

def set_led(led, on_or_off):
    if on_or_off:
        led.on()
    else:
        led.off()

def fetch_pulse_measurement():
    """
    Fetch depth, return pulse delay in us
    """
    set_led(led1, 1)

    trig.value(0)
    sleep_us(10)
    trig.value(1)
    sleep_us(10) #Trigger pulse
    trig.value(0) #Restore

    pulse = time_pulse_us(echo, 1, 30000)
    print('Pulse usecs:', pulse)

    set_led(led1, 0)
    return pulse

# This would be periodically polling a hardware sensor.
async def sensor_task():

    while True:
        pulse = fetch_pulse_measurement()
        update_pulse_val(pulse)

        depth = sofs * pulse / 20000 #Depth cms
        print('Surface at', depth, 'cms')
        update_distance(depth)

        await asyncio.sleep_ms(1000)


# Serially wait for connections. Don't advertise while a central is
# connected.
async def peripheral_task():
    while True:
        async with await aioble.advertise(
            _ADV_INTERVAL_MS,
            name="mpy-depth",
            services=[_ENV_SENSE_UUID],
            appearance=_ADV_APPEARANCE_GENERIC_THERMOMETER,
        ) as connection:
            set_led(led0, 1)
            print("Connection from", connection.device)
            await connection.disconnected(timeout_ms=None)
            set_led(led0, 0)

# Run both tasks.
async def main():
    t1 = asyncio.create_task(sensor_task())
    t2 = asyncio.create_task(peripheral_task())
    await asyncio.gather(t1, t2)


asyncio.run(main())
