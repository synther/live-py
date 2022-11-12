import abc
import dataclasses
from typing import List, Optional, Tuple, ClassVar

from . import device_control_events
from .base import DeviceControl
from .device_control_events import DeviceControlEvent

@dataclasses.dataclass
class MidiDeviceControl(DeviceControl, abc.ABC):
    midi_msg_type: ClassVar[Tuple[str, ...]]
    midi_input: str

    @abc.abstractmethod
    def midi_to_device_event(self, msg) -> Optional[DeviceControlEvent]:
        ...

@dataclasses.dataclass
class MidiNoteOnDeviceControl(MidiDeviceControl):
    yaml_type = 'midi_note_on'
    midi_msg_type = ('note_on',)
    midi_channel: int
    midi_note: int

    def midi_to_device_event(self, msg):
        assert msg.type == 'note_on'
        return device_control_events.MidiNoteOnDeviceControlEvent(self, msg.velocity)


@dataclasses.dataclass
class MidiNoteOffDeviceControl(MidiDeviceControl):
    yaml_type = 'midi_note_off'
    midi_msg_type = ('note_off',)
    midi_channel: int
    midi_note: int

    def midi_to_device_event(self, msg):
        assert msg.type == 'note_off'
        return device_control_events.MidiNoteOffDeviceControlEvent(self, msg.velocity)


@dataclasses.dataclass
class MidiNoteDeviceControl(MidiDeviceControl):
    yaml_type = 'midi_note'
    midi_msg_type = ('note_on', 'note_off')
    midi_channel: int
    midi_note: int

    def midi_to_device_event(self, msg):
        assert msg.type in ('note_on', 'note_off')
        velocity = msg.velocity if msg.type == 'note_on' else 0
        return device_control_events.MidiNoteDeviceControlEvent(self, velocity)
