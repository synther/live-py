from typing import Dict, Iterable

from . import yaml_device_controls
from .base import Device, DeviceControl


def create_device(yaml_obj: Dict):
    device_name = next(iter(yaml_obj.values()))
    device = Device()
    devices[device_name] = device

    for control_id, control_props in yaml_obj['controls'].items():
        match control_props['type']:
            case 'midi_note_on':
                device.controls[control_id] = yaml_device_controls.MidiNoteOnDeviceControl(
                    device_name=device_name,
                    control_id=control_id,
                    midi_input=control_props['input'],
                    midi_channel=control_props['channel'],
                    midi_note=control_props['note'],
                )

            case 'midi_note':
                device.controls[control_id] = yaml_device_controls.MidiNoteDeviceControl(
                    device_name=device_name,
                    control_id=control_id,
                    midi_input=control_props['input'],
                    midi_channel=control_props['channel'],
                    midi_note=control_props['note'],
                )

def get_controls(device_name: str) -> Iterable[DeviceControl]:
    return devices[device_name].controls.values()

devices: Dict[str, Device] = {}
