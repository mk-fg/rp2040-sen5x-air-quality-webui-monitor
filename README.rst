RP2040 SEN5x Air Quality WebUI Monitor
======================================

Self-contained micropython_ script for `RP2040-based controllers`_
(e.g. `Raspberry Pi Pico`_ and its clones, but might work on non-RP2xxx devices too)
to monitor air quality parameters (VOC, PM1.0, PM2.5, PM4, PM10 and such),
using connected I2C Sensirion SEN5x sensor (e.g. SEN54_ or `SEN54 in a box`_)
and display/export that data via basic http web interface, with some charts there.

Device is expected to have a WiFi chip for http access, which is also setup by
the script from a `simple ini config`_.

.. contents::
  :backlinks: none

Repository URLs:

- https://github.com/mk-fg/rp2040-sen5x-air-quality-webui-monitor
- https://codeberg.org/mk-fg/rp2040-sen5x-air-quality-webui-monitor
- https://fraggod.net/code/git/rp2040-sen5x-air-quality-webui-monitor

.. _micropython: https://docs.micropython.org/en/latest/
.. _RP2040-based controllers: https://en.wikipedia.org/wiki/RP2040
.. _Raspberry Pi Pico:
  https://www.raspberrypi.com/documentation/microcontrollers/raspberry-pi-pico.html
.. _SEN54: https://sensirion.com/products/catalog/SEN54
.. _SEN54 in a box:
  https://www.seeedstudio.com/Grove-All-in-one-Environmental-Sensor-SEN54-p-5374.html
.. _simple ini config: config.example.ini


How to use this
---------------


All functionality on the device is implemented by the `main.py script`_,
which needs following things in order to work:

- `Micropython firmware`_ installed on the microcontroller (RP2040 or other supported one).

  `Download page`_ for it has a silly-long list of supported devices,
  with their own install links/instructions/notes, but on RP2040 it goes something like this:

  - Pick/download the right .uf2 file (e.g. `from rp2-pico-w page`_ for RPi Pico W likes).
  - Connect tiny board with BOOTSEL switch pressed on boot (or something like it),
    so that it will appear as a USB mass storage device (aka flash drive or usb-stick).
  - Copy UF2 file there, it'll auto-reboot into micropython as soon as copying is done.

  For all further interactions with the thing, I'd recommend installing official
  mpremote_ tool (use pipx_ for clean installs). Running it should get a python
  shell prompt on connected device, it allows to copy/run files there easily,
  and is used in all examples below.

- ``config.ini`` file with configuration parameters, uploaded to device.

  See config.example.ini_ file in the repository, copy/edit that (basic `ini file`_),
  and upload using e.g. ``mpremote cp config.ini :`` command (mpremote_ tool).

  Might be a good idea to enable all verbose=yes options there for the first run.

- Optional step, to actually see data the browser - upload ``webui.js.gz``,
  ``d3.v7.min.js.gz``, ``favicon.ico.gz`` files to the device flash as well.

  ``gzip <webui.js >webui.js.gz`` can be used to make compressed version of
  the frontend JS code and upload that instead of ``webui.js`` for efficiency,
  but either one should work.

  Without these files, WebUI will only display data download links.

Main script can be started via mpremote like this: ``mpremote run main.py``

Should log messages/errors over USB /dev/ttyACMx or UART to mpremote or any
other serial tool connected there (like screen_ or minicom_), esp. if verbose
logging is enabled in config sections, and also connect to network as configured
(or log why not), with its WebUI accessible via usual ``http://<ip-addr>`` URL
(note - http: only, not https: - at least not at the moment).

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

See `Repository contents`_ section below for more information on other optional files.

.. _main.py script: main.py
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


Repository contents
-------------------

Aside from documentation (like this README), useful files in the repository are:

- main.py_ - micropython script to run on the device.

  Runs 3 main components (as asyncio tasks) - WiFi scanner/monitor and
  SSID-picker, I2C sensor data poller, http server for WebUI and data exports.

- config.example.ini_ - example ini_ configuration file with all parameters,
  and comment lines describing what less obvious ones are for.

  Intended to be used as a template for creating required ``config.ini`` file
  to upload to RP2xxx, but can be also useful to track changes in wrt new features,
  modified defaults and such, when updating to new code from this repo.

- webui.js_ - JavaScript frontend code for WebUI data visualization.

  Sent and runs in the browser as-is, fetches current data in binary format on
  page load, and creates interactive visualization (graphs) for it inside <svg> box.

  Should ideally be uploaded to device in gzip-compressed format, as
  ``webui.js.gz``, to take less flash space, bandwidth, time to send/load, etc.

- ``favicon.ico.gz`` and ``d3.v7.min.js.gz`` - page icon and D3.js_ data
  visualization library, in pre-gzip-compressed form, to serve as-is as a part
  of WebUI from the device.

  Both can be optional - if ``d3-load-from-internet = yes`` is enabled in
  configuration file (default - disabled), then d3 will be loaded from its
  official CDN URL, and missing tab icon is not a big deal.

  D3 is a modular lib, and its ``d3.v7.min.js.gz`` build in the repository only
  includes following components that are used by ``webui.js`` code::

    d3-array d3-axis d3-delaunay d3-scale d3-selection d3-shape

  It can be easily rebuilt from its `d3/d3 source repository`_, by cloning it,
  editing ``src/index.js`` to only import parts used/required by ``webui.js``,
  and rebuilding it with following command (as of v7 releases, at least)::

    npm install . && ./node_modules/.bin/rollup -c
    gzip <dist/d3.min.js >d3.v7.min.js.gz

  Minified D3 version with all of its components can be fetched from
  e.g. https://d3js.org/d3.v7.min.js URL.

  D3 can have breaking changes between major releases (like 7.x.x -> 8.x.x),
  so it's probably best to use last version of a major release that ``webui.js``
  is intended to work with, but newer ones can be selected via ``d3-api = ...``
  opt in ``config.ini``.

.. _main.py: main.py
.. _ini: https://en.wikipedia.org/wiki/INI_file
.. _webui.js: webui.js
.. _D3.js: https://d3js.org/
.. _d3/d3 source repository: https://github.com/d3/d3


Links
-----

- ESPHome_ - more comprehensive home automation system,
  which also supports SEN5x sensors connected to RP2040 platforms.

- `Sensirion/python-i2c-sen5x`_ - SEN5x vendor python driver code and examples (not used here).

.. _ESPHome: https://esphome.io/components/sensor/sen5x.html
.. _Sensirion/python-i2c-sen5x: https://github.com/Sensirion/python-i2c-sen5x


TODO
----

- Wiring diagrams, screenshot or somesuch images here.
- Sensor error flags listed on the index page.
- Check CSP options for loading d3 from CDN, might be broken.
- More mobile-friendly WebUI visualizations.
- Look into adding optional http tls wrapping, for diff variety of browser warnings.
