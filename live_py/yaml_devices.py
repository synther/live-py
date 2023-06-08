import logging
from typing import Dict, Iterable, List, Set

from . import yaml_namespace
from .base import Device, DeviceControl
from .yaml_device_controls import MidiDeviceControl

logger = logging.getLogger(__name__)


def get_controls(device_name: str) -> Iterable[DeviceControl]:
    device = yaml_namespace.get_obj(device_name)
    assert isinstance(device, Device)
    return device.controls


def find_controls_by_mido_msg(midi_device_name: str, msg) -> List[MidiDeviceControl]:
    # TODO It's O(n) now, fix later

    controls = []

    for device in yaml_namespace.find_by_class(Device):
        assert isinstance(device, Device)

        for control in device.controls:
            if isinstance(control, MidiDeviceControl) and \
               midi_device_name == control.midi_input and \
               control.match_mido_msg(msg):
                controls.append(control)

    return controls


def find_midi_inputs() -> Set[str]:
    midi_inputs = set()

    for device in yaml_namespace.find_by_class(Device):
        assert isinstance(device, Device)

        for control in device.controls:
            assert isinstance(control, MidiDeviceControl)
            midi_inputs.add(control.midi_input)

    return midi_inputs


yaml_namespace.register_class('device', Device)
