****************************
Mopidy-PiDiV2
****************************

.. image:: https://img.shields.io/pypi/v/Mopidy-PiDiV2.svg
    :target: https://pypi.org/project/Mopidy-PiDiV2/
    :alt: Latest PyPI version

.. image:: https://img.shields.io/circleci/build/gh/pimoroni/mopidy-pidiv2/master.svg
    :target: https://circleci.com/gh/pimoroni/mopidy-pidiv2
    :alt: Travis CI build status

.. image:: https://img.shields.io/codecov/gh/pimoroni/mopidy-pidiv2/master.svg
    :target: https://codecov.io/gh/pimoroni/mopidy-pidiv2
   :alt: Test coverage

Mopidy extension for displaying song info and album art using pidiv2 display plugins.

Mopidy PiDiV2 In Action
=====================

Using our `pidiv2-display-st7789 <https://github.com/pimoroni/pidiv2-plugins/tree/master/pidiv2-display-st7789>`_ plugin Mopidy PiDiV2 will run the display on our `Pirate Audio boards <https://shop.pimoroni.com/collections/pirate-audio>`_, giving you album art and transport info.

.. image:: https://cdn.shopify.com/s/files/1/0174/1800/products/pirate-audio-1_1024x1024.jpg?v=1574158580
   :target: https://shop.pimoroni.com/collections/pirate-audio
   :alt: Pirate Audio Display Boards
   
Combine this with `Mopidy Raspberry GPIO <https://github.com/pimoroni/mopidy-raspberry-gpio>`_ to handle button inputs and you've got a mini music player.

Installation
============

Install by running::

    pip3 install Mopidy-PiDiV2

Or, if available, install the Debian/Ubuntu package from `apt.mopidy.com
<https://apt.mopidy.com/>`_.

You must then install a display plugin, for example::

    pip3 install pidiv2-display-st7789

Find more plugins here: https://github.com/pimoroni/pidiv2-plugins


Configuration
=============

Before starting Mopidy, you must add configuration for
Mopidy-PiDiV2 to your Mopidy configuration file::

    [pidiv2]
    enabled = true
    display = st7789

This example uses st7789 provided by pidiv2-display-st7789


Project resources
=================

- `Source code <https://github.com/pimoroni/mopidy-pidiv2>`_
- `Issue tracker <https://github.com/pimoroni/mopidy-pidiv2/issues>`_
- `Changelog <https://github.com/pimoroni/mopidy-pidiv2/blob/master/CHANGELOG.rst>`_


Credits
=======

- Original author: `Phil Howard <https://github.com/pimoroni>`__
- Current maintainer: `Phil Howard <https://github.com/pimoroni>`__
- `Contributors <https://github.com/pimoroni/mopidy-pidiv2/graphs/contributors>`_
