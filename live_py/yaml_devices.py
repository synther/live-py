from typing import Dict, Iterable, List, Set

from . import yaml_device_controls
from .base import Device, DeviceControl
from .yaml_device_controls import MidiDeviceControl


def create_device(yaml_obj: Dict):
    device_name = next(iter(yaml_obj.values()))
    device = Device()
    devices[device_name] = device

    device.controls.update(yaml_device_controls.create_controls_from_yaml(
        yaml_obj['controls'], device_name
    ))


def get_controls(device_name: str) -> Iterable[DeviceControl]:
    return devices[device_name].controls.values()


devices: Dict[str, Device] = {}


def find_controls_by_mido_msg(midi_device_name: str, msg) -> List[MidiDeviceControl]:
    # TODO It's O(n) now, fix later

    controls = []

    for device in devices.values():
        for control in device.controls.values():
            if isinstance(control, MidiDeviceControl) and \
               midi_device_name == control.midi_input and \
               control.match_mido_msg(msg):
                controls.append(control)

    return controls


def find_midi_inputs() -> Set[str]:
    midi_inputs = set()

    for device in devices.values():
        for control in device.controls.values():
            if isinstance(control, MidiDeviceControl):
                midi_inputs.add(control.midi_input)

    return midi_inputs
