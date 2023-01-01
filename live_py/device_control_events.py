import dataclasses

from .base import DeviceControlEvent


@dataclasses.dataclass
class MidiNoteOnDeviceControlEvent(DeviceControlEvent):
    velocity: int


@dataclasses.dataclass
class MidiNoteOffDeviceControlEvent(DeviceControlEvent):
    velocity: int


@dataclasses.dataclass
class MidiNoteDeviceControlEvent(DeviceControlEvent):
    velocity: int


@dataclasses.dataclass
class MidiCcDeviceControlEvent(DeviceControlEvent):
    value: int
