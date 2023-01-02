import abc
import dataclasses
from typing import ClassVar, Optional, Tuple

from . import device_control_events, yaml_namespace
from .base import DeviceControl
from .device_control_events import DeviceControlEvent


class MidiDeviceControl(DeviceControl, abc.ABC):
    mido_msg_type: ClassVar[Tuple[str, ...]]
    midi_input: str

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj)
        self.midi_input = yaml_obj['input']
        # TODO rename "input" to "midi_device"

    @abc.abstractmethod
    def midi_to_device_event(self, msg) -> Optional[DeviceControlEvent]:
        ...

    @abc.abstractmethod
    def match_mido_msg(self, msg) -> bool:
        ...


class MidiChannelDeviceControl(MidiDeviceControl):
    yaml_type = 'midi_channel'
    mido_msg_type = ('note_on', 'note_off', 'control_change')
    midi_channel: int

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj)
        self.midi_channel = yaml_obj['channel']

    def midi_to_device_event(self, msg) -> Optional[DeviceControlEvent]:
        match msg.type:
            case 'note_on':
                return device_control_events.MidiNoteOnDeviceControlEvent(
                    control=self,
                    velocity=msg.velocity,
                    note=msg.note,
                    channel=msg.channel,
                )

            case 'note_off':
                return device_control_events.MidiNoteOffDeviceControlEvent(
                    control=self,
                    velocity=msg.velocity,
                    note=msg.note,
                    channel=msg.channel,
                )

            case 'control_change':
                return device_control_events.MidiCcDeviceControlEvent(
                    control=self,
                    cc=msg.control,
                    value=msg.value,
                    channel=msg.channel,
                )

        return None

    def match_mido_msg(self, msg) -> bool:
        return msg.type in self.mido_msg_type and \
            msg.channel == self.midi_channel


@dataclasses.dataclass
class MidiNoteOnDeviceControl(MidiChannelDeviceControl):
    yaml_type = 'midi_note_on'
    mido_msg_type = ('note_on',)
    midi_note: int

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj)
        self.midi_note = yaml_obj['note']

    def midi_to_device_event(self, msg):
        assert msg.type in self.mido_msg_type
        return device_control_events.MidiNoteOnDeviceControlEvent(
            control=self,
            velocity=msg.velocity,
            note=msg.note,
            channel=msg.channel,
        )

    def match_mido_msg(self, msg) -> bool:
        return msg.type in self.mido_msg_type and \
            msg.channel == self.midi_channel and \
            msg.note == self.midi_note


@dataclasses.dataclass
class MidiNoteOffDeviceControl(MidiChannelDeviceControl):
    yaml_type = 'midi_note_off'
    mido_msg_type = ('note_off',)
    midi_note: int

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj)
        self.midi_note = yaml_obj['note']

    def midi_to_device_event(self, msg):
        assert msg.type in self.mido_msg_type
        return device_control_events.MidiNoteOffDeviceControlEvent(
            control=self,
            velocity=msg.velocity,
            note=msg.note,
            channel=msg.channel,
        )

    def match_mido_msg(self, msg) -> bool:
        return msg.type in self.mido_msg_type and \
            msg.channel == self.midi_channel and \
            msg.note == self.midi_note


@dataclasses.dataclass
class MidiNoteDeviceControl(MidiChannelDeviceControl):
    yaml_type = 'midi_note'
    mido_msg_type = ('note_on', 'note_off')
    midi_note: int

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj)
        self.midi_note = yaml_obj['note']

    def midi_to_device_event(self, msg):
        assert msg.type in self.mido_msg_type
        velocity = msg.velocity if msg.type == 'note_on' else 0
        return device_control_events.MidiNoteDeviceControlEvent(
            control=self,
            velocity=velocity,
            note=msg.note,
            channel=msg.channel,
        )

    def match_mido_msg(self, msg) -> bool:
        return msg.type in self.mido_msg_type and \
            msg.channel == self.midi_channel and \
            msg.note == self.midi_note


@dataclasses.dataclass
class MidiCcDeviceControl(MidiChannelDeviceControl):
    yaml_type = 'midi_cc'
    mido_msg_type = ('control_change', )
    midi_control: int

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj)
        self.midi_control = yaml_obj['cc']

    def midi_to_device_event(self, msg) -> Optional[DeviceControlEvent]:
        assert msg.type in self.mido_msg_type
        return device_control_events.MidiCcDeviceControlEvent(
            control=self,
            cc=msg.control,
            value=msg.value,
            channel=msg.channel,
        )

    def match_mido_msg(self, msg) -> bool:
        return msg.type in self.mido_msg_type and \
            msg.channel == self.midi_channel and \
            msg.control == self.midi_control


yaml_namespace.register_class(MidiChannelDeviceControl.yaml_type,
                              MidiChannelDeviceControl)

yaml_namespace.register_class(MidiNoteOnDeviceControl.yaml_type,
                              MidiNoteOnDeviceControl)

yaml_namespace.register_class(MidiNoteOffDeviceControl.yaml_type,
                              MidiNoteOffDeviceControl)

yaml_namespace.register_class(MidiNoteDeviceControl.yaml_type,
                              MidiNoteDeviceControl)

yaml_namespace.register_class(MidiCcDeviceControl.yaml_type,
                              MidiCcDeviceControl)
