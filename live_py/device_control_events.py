import dataclasses
from typing import Optional

from .base import DeviceControlEvent


@dataclasses.dataclass
class MidiControlEvent(DeviceControlEvent):
    midi_device: Optional[str]


@dataclasses.dataclass
class MidiClockEvent(MidiControlEvent):
    pass


@dataclasses.dataclass
class MidiStartEvent(MidiControlEvent):
    pass


@dataclasses.dataclass
class MidiStopEvent(MidiControlEvent):
    pass


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
