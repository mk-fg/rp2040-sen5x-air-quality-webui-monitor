RP2040 SEN5x Air Quality WebUI Monitor
======================================

Micropython_ script for `RP2040-based controllers`_ (e.g. `Raspberry Pi Pico`_
and its clones, but might work on non-RP2xxx devices too) to monitor air quality
parameters (VOC, PM1.0, PM2.5, PM4, PM10 and such), using connected I2C Sensirion
SEN5x sensor (e.g. SEN54_ or `SEN54 in a box`_) and display/export that data via
simple http(s) web interface, with a nice chart there.

Network connection is also setup by the script from a `simple ini config`_.

Implementation status and roadmap:

- ☒ - Basic WiFi network configuration / roaming
- ☒ - I2C sensor communication/polling with verbose=yes console logging
- ☒ - I2C error handling and rate-limiting
- ☐ - WebUI raw data export
- ☐ - WebUI tables
- ☐ - WebUI chart(s)
- ☐ - Basic info on how to connect stuff, diagrams/images

.. contents::
  :backlinks: none

Repository URLs:

- https://github.com/mk-fg/rp2040-sen5x-air-quality-webui-monitor
- https://codeberg.org/mk-fg/rp2040-sen5x-air-quality-webui-monitor
- https://fraggod.net/code/git/rp2040-sen5x-air-quality-webui-monitor

.. _Micropython: https://docs.micropython.org/en/latest/
.. _RP2040-based controllers: https://en.wikipedia.org/wiki/RP2040
.. _Raspberry Pi Pico:
  https://www.raspberrypi.com/documentation/microcontrollers/raspberry-pi-pico.html
.. _SEN54: https://sensirion.com/products/catalog/SEN54
.. _SEN54 in a box:
  https://www.seeedstudio.com/Grove-All-in-one-Environmental-Sensor-SEN54-p-5374.html
.. _simple ini config: config.example.ini


Links
-----

- ESPHome_ - more comprehensive home automation system,
  which also supports SEN5x sensors connected to RP2040 platforms.

- `Sensirion/python-i2c-sen5x`_ - SEN5x vendor python driver code and examples (not used here).

.. _ESPHome: https://esphome.io/components/sensor/sen5x.html
.. _Sensirion/python-i2c-sen5x: https://github.com/Sensirion/python-i2c-sen5x
