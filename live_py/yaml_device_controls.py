import abc
import dataclasses
from typing import Any, ClassVar, Dict, Optional, Tuple, Type

from . import device_control_events
from .base import DeviceControl
from .device_control_events import DeviceControlEvent


@dataclasses.dataclass
class MidiDeviceControl(DeviceControl, abc.ABC):
    mido_msg_type: ClassVar[Tuple[str, ...]]
    midi_input: str

    @abc.abstractmethod
    def midi_to_device_event(self, msg) -> Optional[DeviceControlEvent]:
        ...

    @abc.abstractmethod
    def match_mido_msg(self, msg) -> bool:
        ...


@dataclasses.dataclass
class MidiNoteOnDeviceControl(MidiDeviceControl):
    yaml_type = 'midi_note_on'
    mido_msg_type = ('note_on',)
    midi_channel: int
    midi_note: int

    def midi_to_device_event(self, msg):
        assert msg.type in self.mido_msg_type
        return device_control_events.MidiNoteOnDeviceControlEvent(self, msg.velocity)

    def match_mido_msg(self, msg) -> bool:
        return msg.type in self.mido_msg_type and \
            msg.channel == self.midi_channel and \
            msg.note == self.midi_note

    @classmethod
    def create_from_yaml(cls, device_name: str, control_id: int, control_props: Dict[str, Any]):
        return MidiNoteOnDeviceControl(
            device_name=device_name,
            control_id=control_id,
            midi_input=control_props['input'],
            midi_channel=control_props['channel'],
            midi_note=control_props['note'],
        )


@dataclasses.dataclass
class MidiNoteOffDeviceControl(MidiDeviceControl):
    yaml_type = 'midi_note_off'
    mido_msg_type = ('note_off',)
    midi_channel: int
    midi_note: int

    def midi_to_device_event(self, msg):
        assert msg.type in self.mido_msg_type
        return device_control_events.MidiNoteOffDeviceControlEvent(self, msg.velocity)

    def match_mido_msg(self, msg) -> bool:
        return msg.type in self.mido_msg_type and \
            msg.channel == self.midi_channel and \
            msg.note == self.midi_note

    @classmethod
    def create_from_yaml(cls, device_name: str, control_id: int, control_props: Dict[str, Any]):
        return MidiNoteOffDeviceControl(
            device_name=device_name,
            control_id=control_id,
            midi_input=control_props['input'],
            midi_channel=control_props['channel'],
            midi_note=control_props['note'],
        )


@dataclasses.dataclass
class MidiNoteDeviceControl(MidiDeviceControl):
    yaml_type = 'midi_note'
    mido_msg_type = ('note_on', 'note_off')
    midi_channel: int
    midi_note: int

    def midi_to_device_event(self, msg):
        assert msg.type in self.mido_msg_type
        velocity = msg.velocity if msg.type == 'note_on' else 0
        return device_control_events.MidiNoteDeviceControlEvent(self, velocity)

    def match_mido_msg(self, msg) -> bool:
        return msg.type in self.mido_msg_type and \
            msg.channel == self.midi_channel and \
            msg.note == self.midi_note

    @classmethod
    def create_from_yaml(cls, device_name: str, control_id: int, control_props: Dict[str, Any]):
        return MidiNoteDeviceControl(
            device_name=device_name,
            control_id=control_id,
            midi_input=control_props['input'],
            midi_channel=control_props['channel'],
            midi_note=control_props['note'],
        )


@dataclasses.dataclass
class MidiCcDeviceControl(MidiDeviceControl):
    yaml_type = 'midi_cc'
    mido_msg_type = ('control_change', )
    midi_channel: int
    midi_control: int

    def midi_to_device_event(self, msg) -> Optional[DeviceControlEvent]:
        assert msg.type in self.mido_msg_type
        return device_control_events.MidiCcDeviceControlEvent(self, msg.value)

    def match_mido_msg(self, msg) -> bool:
        return msg.type in self.mido_msg_type and \
            msg.channel == self.midi_channel and \
            msg.control == self.midi_control

    @classmethod
    def create_from_yaml(cls, device_name: str, control_id: int, control_props: Dict[str, Any]):
        return MidiCcDeviceControl(
            device_name=device_name,
            control_id=control_id,
            midi_input=control_props['input'],
            midi_channel=control_props['channel'],
            midi_control=control_props['control'],
        )


def create_controls_from_yaml(controls_yaml: Dict, device_name: str) -> Dict[int, DeviceControl]:
    device_controls = {}

    device_control_classes: Dict[str, Type[DeviceControl]] = {
        cls.yaml_type: cls for cls in [
            MidiNoteOnDeviceControl,
            MidiNoteOffDeviceControl,
            MidiNoteDeviceControl,
            MidiCcDeviceControl,
        ]
    }

    for control_id, control_props in controls_yaml.items():
        device_control = None

        device_control_class = device_control_classes.get(control_props['type'])

        if device_control_class:
            device_control = device_control_class.create_from_yaml(
                device_name,
                control_id,
                control_props
            )

        if device_control:
            device_controls[control_id] = device_control

    return device_controls
