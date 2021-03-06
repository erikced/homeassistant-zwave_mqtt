"""Support for Z-Wave lights."""
import logging

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    SUPPORT_BRIGHTNESS,
    SUPPORT_TRANSITION,
    Light,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .entity import ZWaveDeviceEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up Z-Wave Light from Config Entry."""

    @callback
    def async_add_light(values):
        """Add Z-Wave Light."""
        light = ZwaveDimmer(values)
        async_add_entities([light])

    async_dispatcher_connect(hass, "zwave_new_light", async_add_light)

    await hass.data[DOMAIN][config_entry.entry_id]["mark_platform_loaded"]("light")


def byte_to_zwave_brightness(value):
    """Convert brightness in 0-255 scale to 0-99 scale.

    `value` -- (int) Brightness byte value from 0-255.
    """
    if value > 0:
        return max(1, int((value / 255) * 99))
    return 0


class ZwaveDimmer(ZWaveDeviceEntity, Light):
    """Representation of a Z-Wave dimmer."""

    def __init__(self, values):
        """Initialize the light."""
        ZWaveDeviceEntity.__init__(self, values)
        self._supported_features = None
        self.value_added()

    @callback
    def value_added(self):
        """Call when a new value is added to this entity."""
        self._supported_features = SUPPORT_BRIGHTNESS
        if self.values.dimming_duration is not None:
            self._supported_features |= SUPPORT_TRANSITION

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        if "target" in self.values:
            return round((self.values.target.value / 99) * 255)
        return round((self.values.primary.value / 99) * 255)

    @property
    def is_on(self):
        """Return true if device is on (brightness above 0)."""
        return self.values.primary.value > 0

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    async def async_set_duration(self, **kwargs):
        """Set the transition time for the brightness value.

        Zwave Dimming Duration values:
        0x00      = instant
        0x01-0x7F = 1 second to 127 seconds
        0x80-0xFE = 1 minute to 127 minutes
        0xFF      = factory default
        """
        if self.values.dimming_duration is None:
            if ATTR_TRANSITION in kwargs:
                _LOGGER.debug("Dimming not supported by %s.", self.entity_id)
            return

        if ATTR_TRANSITION not in kwargs:
            self.values.dimming_duration.send_value(0xFF)
            return

        transition = kwargs[ATTR_TRANSITION]
        if transition <= 127:
            self.values.dimming_duration.send_value(int(transition))
        elif transition > 7620:
            self.values.dimming_duration.send_value(0xFE)
            _LOGGER.warning("Transition clipped to 127 minutes for %s.", self.entity_id)
        else:
            minutes = int(transition / 60)
            _LOGGER.debug(
                "Transition rounded to %d minutes for %s.", minutes, self.entity_id
            )
            self.values.dimming_duration.send_value(minutes + 0x7F)

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        await self.async_set_duration(**kwargs)

        # Zwave multilevel switches use a range of [0, 99] to control
        # brightness. Level 255 means to set it to previous value.
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            brightness = byte_to_zwave_brightness(brightness)
        else:
            brightness = 255

        self.values.primary.send_value(brightness)

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        await self.async_set_duration(**kwargs)

        self.values.primary.send_value(0)
