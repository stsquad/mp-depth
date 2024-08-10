from machine import Pin,time_pulse_us,Timer
from time import sleep_us

# 4 bit display in LEDs
led0 = Pin(14, Pin.OUT)
led1 = Pin(15, Pin.OUT)
led2 = Pin(17, Pin.OUT)
led3 = Pin(16, Pin.OUT)

active = Pin(12, Pin.IN)

sofs = 340 #Speed of sound in air m/s

echo = Pin(0, Pin.IN)
trig = Pin(1, Pin.OUT)

def set_led(led, on_or_off):
    if on_or_off:
        led.on()
    else:
        led.off()

#Test bed for Pond Depth Gauge 1/7/24
#I think the Pico WiFi is better than the RPi0W

counter = 0

while True:

    active.value(1)

    trig.value(0)
    sleep_us(10)
    trig.value(1)
    sleep_us(10) #Trigger pulse
    trig.value(0) #Restore


    pulse = time_pulse_us(echo,1,30000)
    active.value(0)

    print('Pulse usecs ',pulse)
    depth = sofs * pulse / 20000 #Depth cms
    print('Surface at',depth,'cms')

    counter = (counter + 1) % 0xf
    set_led(led0, counter & 1)
    set_led(led1, counter & 2)
    set_led(led2, counter & 4)
    set_led(led3, counter & 8)
    sleep_us(10)
    set_led(led0, 0)
    set_led(led1, 0)
    set_led(led2, 0)
    set_led(led3, 0)

    sleep_us(10000)
