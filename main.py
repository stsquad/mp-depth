#
# mp-depth - a BLE depth sensor written in micropython
#
# Copyright (C) 2024 Alex Bennée
#
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import bluetooth
import struct
import binascii

from micropython import const
from machine import Pin,time_pulse_us,Timer
from time import sleep_us

# ADV_TYPES are defined in assigned_numbers/core/ad_types.yaml
ADV_TYPE_FLAGS = const(0x01)
ADV_TYPE_SNAME = const(0x08) # shortened local name
ADV_TYPE_CNAME = const(0x09) # complete local name
ADV_TYPE_SDATA = const(0x16) # service data

# BTHome UUID (via Allterco Robotics ltd in member_uuids.yaml)
BTHOME_UUID = bluetooth.UUID(0xFCD2)

# How frequently to poll data
POLL_INTERVAL_MS = 1_000

# How frequently to send BT beacons
BT_BEACON_INTERVAL_MS = 5_000

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

def create_adv_frame(adv_type, adv_data):
    """
    Return the bytes for a single advertising frame in the PDU
    """
    l = len(adv_data)
    print(f"type: {adv_type}, data: {adv_data}/{l}")
    return struct.pack("BB", l + 1, adv_type) + adv_data


def create_bthome_frame(pulse, depth):
    """
    Create a BTHome frame. This will be the data part of the
    advertising packet identifying the BTHome device and supplying the
    measurements.

    We don't support connections, everything should be broadcast in
    the advert.
    """
    payload = bytearray()

    # Flags value (fixed for BTHome)
    # bit 1/0x2 - LE General Discoverable Mode
    # bit 2/0x4 - BR/EDR Not Supported
    payload += create_adv_frame(ADV_TYPE_FLAGS, bytearray([0x6]))

    # We can include common headers (name etc)
    payload += create_adv_frame(ADV_TYPE_CNAME, b'depth')

    # BTHome header
    bthome = bytearray(BTHOME_UUID)
    # not encrypted, regular updates, version 2
    bthome.extend(struct.pack("<B", 0x40))

    # Pulse width
    pulse_as_hex = hex(pulse)
    bthome.extend(struct.pack("<B", 0x54)) # raw
    bthome.extend(struct.pack("<B", len(pulse_as_hex)))
    bthome.extend(bytes(pulse_as_hex, 'ascii'))

    # Calculated depth
    depth_as_hex = hex(depth)
    bthome.extend(struct.pack("<B", 0x54)) # raw
    bthome.extend(struct.pack("<B", len(depth_as_hex)))
    bthome.extend(bytes(depth_as_hex, 'ascii'))

    print("bthome: %s/%d" % (binascii.hexlify(bthome), len(bthome)))

    # encapsulated in a SERVICE_DATA packet
    payload += create_adv_frame(ADV_TYPE_SDATA, bthome)

    print("payload: %s/%d" % (binascii.hexlify(payload), len(payload)))
    return payload


# This would be periodically polling a hardware sensor.
async def sensor_task(bt):

    while True:
        pulse = fetch_pulse_measurement()
        depth = sofs * pulse / 20000 #Depth cms
        print('Surface at', depth, 'cms')

        payload = create_bthome_frame(pulse, int(depth))

        # I think the underlying library is meant to handle the 16 bit
        # PDU header
        bt.gap_advertise(BT_BEACON_INTERVAL_MS,
                         adv_data = payload,
                         connectable = False)

        await asyncio.sleep_ms(POLL_INTERVAL_MS)


# Run tasks.
async def main():

    bt = bluetooth.BLE()
    bt.active(True)

    bt.config(addr_mode = 0x0,
              gap_name = "depth")

    t1 = asyncio.create_task(sensor_task(bt))
    await asyncio.gather(t1)


asyncio.run(main())
