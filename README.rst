RP2040 SEN5x Air Quality WebUI Monitor
======================================

Self-contained micropython_ script for `RP2040-based controllers`_
(e.g. `Raspberry Pi Pico`_ and its clones, but might work on non-RP2xxx devices too)
to monitor air quality parameters (VOC, PM1.0, PM2.5, PM4, PM10 and such),
using connected I²C Sensirion SEN5x sensor (e.g. SEN54_ or `SEN54 in a box`_)
and display/export that data via basic http web interface, with some charts there.

Device is expected to have a WiFi chip for http access, which is also setup by
the script from a `simple ini config`_.

Intended use is for temporary home air quality control during forest-fire
seasons or periods of weather conducive to smog accumulation, and to check which
measures are effective at minimizing exposure to such pollution in specific areas
(e.g. how much air circulation to cut off, when to best close windows, effects
of other factors like air washers and indoor humidity, etc).

.. contents::
  :backlinks: none

Repository URLs:

- https://github.com/mk-fg/rp2040-sen5x-air-quality-webui-monitor
- https://codeberg.org/mk-fg/rp2040-sen5x-air-quality-webui-monitor
- https://fraggod.net/code/git/rp2040-sen5x-air-quality-webui-monitor

Built-in WebUI should look/work something like this:

  https://mk-fg.github.io/rp2040-sen5x-air-quality-webui-monitor/docs/index.html

Or here's a screenshot of how it looks, as of bf06d86 / 2023-07-02 (might be old):

.. image:: https://mk-fg.github.io/rp2040-sen5x-air-quality-webui-monitor/docs/screenshot.jpg
   :width: 100%
   :align: center

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

  - Pick/download the right .uf2 file (`from rp2-pico-w page`_ for RPi Pico W likes).
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

  Wi-Fi SSID configuration can be left blank to not configure WLAN interface,
  in which case script should be able to run on devices that don't have it,
  logging data to console if verbose=yes is enabled in ``[sensor]`` section.

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

``main.py`` can also be compiled into an `.mpy module file`_ to take less
storage space on the flash and start faster - see `Setup to auto-run efficiently
as .mpy file`_ section below for that.

See `Repository contents`_ below for more information on other optional files.

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
.. _.mpy module file: https://docs.micropython.org/en/latest/reference/mpyfiles.html


What to connect where with wires
--------------------------------

Pinout diagram of the device used to run the main script should have I2C
(aka I²C, IIC) bus pins (SDA/SCL for data/clock), as well as GND and 5V voltage
pins (or VBUS/VSYS - same thing as 5V for the purposes of connecting the sensor).

SEN5x should be connected to same SDA/SCL I2C pins, powered via VDD/GND pins,
and have its SEL pin connected to same GND pin as well:

.. image:: https://mk-fg.github.io/rp2040-sen5x-air-quality-webui-monitor/docs/wiring-example.jpg
   :width: 100%
   :align: center

With `Grove interface`_ on `a packaged SEN54 module`_, it's the same idea -
yellow/white wires being I2C SCL/SDA respectively, and red/black are VDD/GND ones.

RP2040 have multiple I2C interfaces, which can be exposed on different pins, all
of which must be specified correctly in the ``config.ini`` file uploaded to flash,
using GP<n> numbers for pins (e.g. 0 as in GP0 instead of number for a physical pin).

For example, with wiring as per `image above`_, following values should be used there::

  [sensor]
  i2c-n = 0
  i2c-pin-sda = 0
  i2c-pin-scl = 1

Board pinouts can usually be found on the vendor site, like `here for RPi Pico W`_.

There is also more info on such stuff in datasheets for these devices.

.. _here for RPi Pico W:
  https://www.raspberrypi.com/documentation/microcontrollers/raspberry-pi-pico.html#pinout-and-design-files-2
.. _Grove interface:
  https://wiki.seeedstudio.com/Grove_System/#interface-of-grove-modules
.. _a packaged SEN54 module:
  https://www.seeedstudio.com/Grove-All-in-one-Environmental-Sensor-SEN54-p-5374.html
.. _image above: https://mk-fg.github.io/rp2040-sen5x-air-quality-webui-monitor/docs/wiring-example.jpg


Repository contents
-------------------

Aside from documentation (like this README), useful files in the repository are:

- main.py_ - micropython script to run on the device.

  Runs 3 main components (as asyncio tasks) - WiFi scanner/monitor and
  SSID-picker, I²C sensor data poller, http server for WebUI and data exports.

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


Data export formats
-------------------

CSV and binary data exports are available via links at the top of WebUI index page.

**CSV** (`comma-separated values`_ plaintext format, .csv file) should be mostly
self-descriptive, with the header containing following columns (and data rows
following that)::

  time_offset, pm10, pm25, pm40, pm100, rh, t, voc, nox

Where ``time_offset`` is a time delta of the sample, in seconds, offset from
current time, as tracked by the micropython's `time.ticks_ms()`_ monotonic timer.
Real-Time Clock (RTC) is not used at the moment, as it is not expected to be set,
so there're only "time from now" offsets available, from the time of http data request,
likely reflected in creation/modification timestamps on the downloaded CSV file.

Due to device performance limitations, CSV file download might take couple
seconds, depending on the data size (number of collected samples, limited by
``sample-count`` config option), as conversion for it is done on the http-server
side, and is not implemented efficiently in the code.

CSV files are supported by pretty much any data-processing software,
and can be imported into common spreadsheet apps like `MS Excel`_.

**Binary data export** (.bin file) is much more compact and efficient than
plaintext CSV above, and consists of concatenated timestamp-sample tuples::

  <data> ::= <data_tuple> <data>
  <data_tuple> ::= <time_offset_ms [double]> <sen5x_sample>
  <sen5x_sample> ::=
    <PM1 µg/m³ *10 [uint16]>
    <PM2.5 µg/m³ *10 [uint16]>
    <PM4 µg/m³ *10 [uint16]>
    <PM10 µg/m³ *10 [uint16]>
    <relative_humidity % *100 [int16]>
    <temperature °C *200 [int16]>
    <VOC *10 [int16]>
    <NOx *10 [int16]>

Note that ``<sen5x_sample>`` values above are exact raw samples as returned by
the connected SEN5x sensor over its I²C interface, and are described in
much more detail in its datasheet (linked on the manufacturer/product page,
e.g. `from SEN54 product page here`_).

All integer values are big-endian, and should be divided by some coefficient
(by 10 for PM values, 100 for RH, 200 for T, etc) to produce actual value -
again, exactly same as described in the sensor datasheet, so check there if in
doubt as to how to interpret those.

``<time_offset_ms>`` is a big-endian double-precision floating-point negative
value, with same meaning as ``time_offset`` field in CSV table described above,
but in milliseconds here instead of seconds.

Such custom binary format should be easy to parse by any code, and is much more
efficient in pretty much all ways than CSV, especially to generate on a potentially
underpowered microcontroller, using multiple orders of magnitude less CPU cycles there.

Samples should be returned in most-recent-first order, but with timestamps in there,
it's more like an implementation detail and shouldn't matter or be relied upon.

.. _comma-separated values: https://en.wikipedia.org/wiki/Comma-separated_values
.. _MS Excel: https://en.wikipedia.org/wiki/Microsoft_Excel
.. _time.ticks_ms(): https://docs.micropython.org/en/latest/library/time.html#time.ticks_ms
.. _from SEN54 product page here: https://sensirion.com/products/catalog/SEN54


Setup to auto-run efficiently as .mpy file
------------------------------------------

main.py is a python script, which normally micropython would have to `parse and
then byte-compile`_ every time before running.

This is useful for testing changes in the script using e.g. ``mpremote run ...``
without extra steps, but when running same script every time board boots,
it's a waste of time, and can be skipped by pre-compiling the script
into .mpy module, which will take less extra work to load.

It can be done something like this:

- Build/install `mpy-cross tool`_ - maybe from an OS package, or from sources.

  It has no significant dependencies, usual "make" should produce
  ``./build/mpy-cross`` binary (see also `Arch PKGBUILD for it here`_).

  .. _mpy-cross tool: https://github.com/micropython/micropython/tree/master/mpy-cross
  .. _Arch PKGBUILD for it here:
    https://github.com/mk-fg/archlinux-pkgbuilds/blob/master/mpy-cross/PKGBUILD

- Run ``mpy-cross -march=armv6m -O2 main.py -o aqm.mpy`` to build ``aqm.mpy``
  module file.

  See `official docs on .mpy files`_ for more info on picking compiler options above.

  .. _official docs on .mpy files:
    https://docs.micropython.org/en/latest/reference/mpyfiles.html#versioning-and-compatibility-of-mpy-files

- Upload produced ``aqm.mpy`` file and test-run it::

    % mpremote cp aqm.mpy :
    % mpremote exec 'import aqm; aqm.run()'

  Should run it same as ``mpremote run main.py``, just a bit faster,
  without any errors or issues.

- Make and upload loader file to run ``aqm.mpy`` on board boot.

  Same code as in "exec" command above can be uploaded to ``main.py`` file on
  the board's flash storage to import/run ``aqm.mpy`` on boot::

    % echo 'import aqm; aqm.run()' >loader.py
    % mpremote cp loader.py :main.py

- ``mpremote reset`` or power-cycle device, check that everything runs correctly.

  If verbose logging is enabled, running ``mpremote`` or connecting to device
  usb-tty should have the same output there as when test-running main.py earlier.

Even more optimization can be done by embedding "frozen bytecode" into board's
micropython firmware image using a manifest file, in which case it will run
directly from flash storage and not use RAM for that - faster, and leaving more
memory to buffer samples (by about 15 KiB I think), but a bit more hassle to
build/upload - see documentation on `MicroPython manifest files`_ for how to do it.

.. _parse and then byte-compile:
  https://docs.micropython.org/en/latest/reference/constrained.html#compilation-phase
.. _MicroPython manifest files:
  https://docs.micropython.org/en/latest/reference/manifest.html


Links
-----

- ESPHome_ - more comprehensive home automation system,
  which also supports SEN5x sensors connected to RP2040 platforms.

- `Sensirion/python-i2c-sen5x`_ - SEN5x vendor python driver code and examples (not used here).

.. _ESPHome: https://esphome.io/components/sensor/sen5x.html
.. _Sensirion/python-i2c-sen5x: https://github.com/Sensirion/python-i2c-sen5x


TODO
----

- Sensor error flags listed on the index page.
- Check CSP options for loading d3 from CDN, might be broken.
- More mobile-friendly WebUI visualizations.
- Look into adding optional http tls wrapping, for diff variety of browser warnings.
- Add option to use RTC for keeping track of time, init it from some network source.
