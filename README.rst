RP2040 SEN5x Air Quality WebUI Monitor
======================================

Micropython_ script for `RP2040-based controllers`_ (e.g. `Raspberry Pi Pico`_
and its clones, but might work on non-RP2xxx devices too) to monitor air quality
parameters (VOC, PM1.0, PM2.5, PM4, PM10 and such), using connected I2C Sensirion
SEN5x sensor (e.g. SEN54_ or `SEN54 in a box`_) and display/export that data via
basic http web interface, with a nice chart there.

Network connection is also setup by the script from a `simple ini config`_.

Doesn't use/need anything else, beyond hardware and what's in micropython already.

Implementation status and roadmap:

- ☒ - Basic WiFi network configuration / roaming
- ☒ - I2C sensor communication/polling with verbose=yes console logging
- ☒ - I2C error handling and rate-limiting
- ☒ - WebUI raw data export
- ☐ - WebUI tables
- ☐ - WebUI chart(s)
- ☐ - Basic info on how to connect/run stuff, diagrams/images

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


How to use this
---------------

`main.py file`_ here is the whole script, which only needs two things to work:

- `Micropython firmware`_ installed on the microcontroller (e.g. RP2040 or similar one).

  `Download page`_ for it has a silly-long list of supported devices,
  but on RP2040 it goes something like this:

  - Pick/download the right .uf2 file (e.g. `from rp2-pico-w page`_ for RPi Pico W likes).
  - Connect tiny board with BOOTSEL switch pressed on boot (or something like it),
    so that it will appear as a USB mass storage device (aka flash drive or usb-stick).
  - Copy UF2 file there, it'll auto-reboot into micropython as soon as copying is done.

  For all further interactions with the thing, I'd recommend installing official
  mpremote_ tool (use pipx_ for clean installs). Running it should get a python
  shell prompt on connected device, it allows to copy/run files there easily,
  and is used in all examples below.

- And ``config.ini`` file with configuration parameters, uploaded to device.

  See config.example.ini_ file in the repository, copy/edit that (basic `ini file`_),
  and upload using e.g. ``mpremote cp config.ini :`` command (mpremote_ tool).

  Might be a good idea to enable all verbose=yes options there for the first run.

Script can be started via mpremote like this: ``mpremote run main.py``

Should log messages/errors over USB /dev/ttyACMx or UART to mpremote or any
other serial tool connected there (like screen_ or minicom_), esp. if verbose
logging is enabled in config sections, and also connect to network as configured
(or log why not), with its WebUI accessible via usual ``http://<ip-addr>`` URL.

  After "run main.py" command, Ctrl-C will stop mpremote showing its output,
  but to actually stop it, either run ``mpremote`` to connect to `repl console`_
  and Ctrl-C-interrupt it there, or e.g. ``mpremote soft-reset`` command.

  Dynamic DHCP addrs should always be logged over serial when they change,
  but there's also an easy way to print those from python anytime, for example::

    % mpremote exec 'import network; print(network.WLAN().ifconfig())'

  Or same thing in the ``>>>`` python prompt on device console.

If ``main.py`` file is copied to the fw storage (next to ``config.ini`` there),
it will be automatically started when device powers-up (must be named either
"main.py" or "boot.py" for that), but can be stopped anytime via terminal in the
same way as with "run" command above - connect and Ctrl-C or soft-reset into REPL_.

.. _main.py file: main.py
.. _Micropython firmware: https://docs.micropython.org/
.. _Download page: https://micropython.org/download/
.. _from rp2-pico-w page: https://micropython.org/download/rp2-pico-w/
.. _mpremote: https://docs.micropython.org/en/latest/reference/mpremote.html
.. _pipx: https://pypa.github.io/pipx/
.. _ini file: https://en.wikipedia.org/wiki/INI_file
.. _config.example.ini: config.example.ini
.. _repl console: https://docs.micropython.org/en/latest/reference/repl.html
.. _screen: https://wiki.archlinux.org/title/GNU_Screen
.. _minicom: https://wiki.archlinux.org/title/Working_with_the_serial_console#Making_Connections
.. _REPL: https://docs.micropython.org/en/latest/reference/repl.html


Links
-----

- ESPHome_ - more comprehensive home automation system,
  which also supports SEN5x sensors connected to RP2040 platforms.

- `Sensirion/python-i2c-sen5x`_ - SEN5x vendor python driver code and examples (not used here).

.. _ESPHome: https://esphome.io/components/sensor/sen5x.html
.. _Sensirion/python-i2c-sen5x: https://github.com/Sensirion/python-i2c-sen5x
