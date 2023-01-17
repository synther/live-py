import dataclasses

from .base import DeviceControlEvent


@dataclasses.dataclass
class MidiControlEvent(DeviceControlEvent):
    midi_device: str


@dataclasses.dataclass
class MidiChannelControlEvent(MidiControlEvent):
    channel: int


@dataclasses.dataclass
class MidiNoteOnDeviceControlEvent(MidiChannelControlEvent):
    velocity: int
    note: int


@dataclasses.dataclass
class MidiNoteOffDeviceControlEvent(MidiChannelControlEvent):
    velocity: int
    note: int


@dataclasses.dataclass
class MidiNoteDeviceControlEvent(MidiChannelControlEvent):
    velocity: int
    note: int


@dataclasses.dataclass
class MidiCcDeviceControlEvent(MidiChannelControlEvent):
    cc: int
    value: int
