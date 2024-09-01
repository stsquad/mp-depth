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

BTHOME_CB_OBJ = const(0x09)
BTHOME_CW_OBJ = const(0x3D)
BTHOME_DIST_MM = const(0x40)
BTHOME_DIST_DM = const(0x41)

# Idle and active polling intervals
IDLE_INTERVAL_MS = 30_000
ACTIVE_INTERVAL_MS = 5_000

# How many active pulses to send left
# when we first power up we start active
active_count = 10
current_interval = ACTIVE_INTERVAL_MS

# Indicator LEDs
led_bt = Pin(14, Pin.OUT)
led_measure = Pin(15, Pin.OUT)
led_active = Pin(17, Pin.OUT)

# Speed of sound in air m/s
# (dependant on pressure)
sofs = 343.0

echo = Pin(0, Pin.IN)
trig = Pin(1, Pin.OUT)

# Wake up and probe button
button = Pin(5, Pin.IN)

def set_led(led, on_or_off):
    if on_or_off:
        led.on()
    else:
        led.off()

def fetch_pulse_measurement():
    """
    Fetch depth, return pulse delay in us
    """
    set_led(led_measure, 1)

    trig.value(0)
    sleep_us(10)

    # Send trigger pulse
    trig.value(1)
    sleep_us(10)
    trig.value(0)

    # Time response
    pulse = time_pulse_us(echo, 1, 30000)
    print('Pulse usecs:', pulse)

    set_led(led_measure, 0)
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

    # Pulse width (Count, 2bytes)
    bthome.extend(struct.pack("<B", BTHOME_CW_OBJ))
    bthome.extend(struct.pack(">H", pulse))

    # Calculated depth (mms)
    if depth > 65535:
        depth_deci_meter = depth / 100
        bthome.extend(struct.pack("<B", BTHOME_DIST_DM))
        bthome.extend(struct.pack(">H", int(depth_deci_meter)))
    else:
        bthome.extend(struct.pack("<B", BTHOME_DIST_MM))
        bthome.extend(struct.pack(">H", int(depth)))

    print("bthome: %s/%d" % (binascii.hexlify(bthome), len(bthome)))

    # encapsulated in a SERVICE_DATA packet
    payload += create_adv_frame(ADV_TYPE_SDATA, bthome)

    print("payload: %s/%d" % (binascii.hexlify(payload), len(payload)))
    return payload

def read_and_send_packet(bt):
    pulse = fetch_pulse_measurement()
    # m/s * s
    depth = sofs * pulse / 2000 #Depth mms
    print('Surface at', depth, 'mms')

    payload = create_bthome_frame(pulse, depth)

    # check if we need to slow down
    global active_count
    global current_interval

    if active_count > 0:
        active_count -= 1
        if active_count == 0:
            current_interval = IDLE_INTERVAL_MS
            set_led(led_active, 0)

    print(f"{active_count} left at {current_interval}")

    # I think the underlying library is meant to handle the 16 bit
    # PDU header
    bt.gap_advertise(current_interval,
                     adv_data = payload,
                     connectable = False)

# This is the periodic sensor task
async def sensor_task(bt):
    """
    Periodic sensor task reading
    """

    while True:
        read_and_send_packet(bt)
        print(f"sleeping for {current_interval}")
        await asyncio.sleep_ms(current_interval)
        print(f"sleep is now {current_interval}")


def handle_button_press(bt):
    """
    When the button is pressed increase the scanning interval for a
    number of collections.
    """
    global current_interval
    global active_count

    current_interval = ACTIVE_INTERVAL_MS
    active_count = min(active_count + 2, 15)

    set_led(led_active, 1)

    read_and_send_packet(bt)

    # this will send an immediate packet but sensor_task will still
    # do its normal cycle


# Run tasks.
async def main():

    bt = bluetooth.BLE()
    bt.active(True)

    bt.config(addr_mode = 0x0,
              gap_name = "depth")

    st = asyncio.create_task(sensor_task(bt))

    set_led(led_active, 1)
    button.irq(lambda p: handle_button_press(bt))

    await asyncio.gather(st)


asyncio.run(main())
