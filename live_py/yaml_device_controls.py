import abc
import dataclasses
import logging
from typing import ClassVar, Optional, Tuple

import mido

from . import device_control_events, yaml_namespace
from .base import DeviceControl, DeviceControlEvent
from .device_control_events import (DeviceControlEvent,
                                    MidiChannelControlEvent, MidiControlEvent,
                                    MidiNoteOffDeviceControlEvent,
                                    MidiNoteOnDeviceControlEvent)

logger = logging.getLogger(__name__)


class MidiDeviceControl(DeviceControl, abc.ABC):
    mido_msg_type: ClassVar[Tuple[str, ...]]
    midi_input: Optional[str]
    midi_output: Optional[str]

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj)
        self.midi_input = yaml_obj.get('input', None)
        self.midi_output = yaml_obj.get('output', None)
        # TODO rename "input" to "midi_device" or add "output"

    @abc.abstractmethod
    def midi_to_device_event(self, msg, device_name: str) -> Optional[DeviceControlEvent]:
        ...

    @abc.abstractmethod
    def match_mido_msg(self, msg) -> bool:
        ...

    def send(self, msg: MidiControlEvent):
        logger.debug(f'Sending {msg} to {self}')

        if self.midi_output:
            msg.midi_device = self.midi_output
            send_midi(msg)
            super().send(msg)
        else:
            logger.warning(f'No "output" property in {self.name} device control to send MIDI')


class MidiChannelDeviceControl(MidiDeviceControl):
    yaml_type = 'midi_channel'
    mido_msg_type = ('note_on', 'note_off', 'control_change')
    midi_channel: int

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj)
        self.midi_channel = yaml_obj['channel']

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.yaml_type=}, {self.midi_channel=}, {self.midi_input=})'

    def send(self, msg: MidiChannelControlEvent):
        logger.debug(f'Sending {msg} to {self}')
        msg.channel = self.midi_channel
        super().send(msg)

    def midi_to_device_event(self, msg, device_name: str) -> Optional[DeviceControlEvent]:
        match msg.type:
            case 'note_on':
                return device_control_events.MidiNoteOnDeviceControlEvent(
                    midi_device=device_name,
                    control=self,
                    velocity=msg.velocity,
                    note=msg.note,
                    channel=msg.channel,
                )

            case 'note_off':
                return device_control_events.MidiNoteOffDeviceControlEvent(
                    midi_device=device_name,
                    control=self,
                    velocity=msg.velocity,
                    note=msg.note,
                    channel=msg.channel,
                )

            case 'control_change':
                return device_control_events.MidiCcDeviceControlEvent(
                    midi_device=device_name,
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

    def send(self, msg: MidiNoteOnDeviceControlEvent):
        logger.debug(f'Sending {msg} to {self}')
        msg.note = self.midi_note
        super().send(msg)

    def midi_to_device_event(self, msg, device_name: str):
        assert msg.type in self.mido_msg_type
        return device_control_events.MidiNoteOnDeviceControlEvent(
            midi_device=device_name,
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

    def midi_to_device_event(self, msg, device_name: str):
        assert msg.type in self.mido_msg_type
        return device_control_events.MidiNoteOffDeviceControlEvent(
            midi_device=device_name,
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

    def midi_to_device_event(self, msg, device_name: str):
        assert msg.type in self.mido_msg_type
        velocity = msg.velocity if msg.type == 'note_on' else 0
        return device_control_events.MidiNoteDeviceControlEvent(
            midi_device=device_name,
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

    def midi_to_device_event(self, msg, device_name: str) -> Optional[DeviceControlEvent]:
        assert msg.type in self.mido_msg_type
        return device_control_events.MidiCcDeviceControlEvent(
            midi_device=device_name,
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


def publish_event_to_subject(event: DeviceControlEvent):
    control = event.control

    if control:
        logger.debug(f"Route {event} to {control.name}.events_in subject")
        control.var_subjects['events_in'].on_next(event)


mido_outputs = {}


def send_midi(msg: device_control_events.DeviceControlEvent):
    mido_msg = None

    if isinstance(msg, device_control_events.MidiNoteOnDeviceControlEvent):
        mido_msg = mido.Message(
            'note_on',
            channel=msg.channel,
            note=msg.note,
            velocity=msg.velocity,
        )
    elif isinstance(msg, device_control_events.MidiNoteOffDeviceControlEvent):
        mido_msg = mido.Message(
            'note_off',
            channel=msg.channel,
            note=msg.note,
            velocity=msg.velocity,
        )
    elif isinstance(msg, device_control_events.MidiCcDeviceControlEvent):
        mido_msg = mido.Message(
            'control_change',
            control=msg.cc,
            value=msg.value,
        )
    else:
        logger.warning(f'Unsupported {msg} ({type(msg)}) to send to MIDI')
        return

    mido_port = mido_outputs.get(msg.midi_device, None)

    if mido_port:
        logger.info(f'Send mido {mido_msg} to "{msg.midi_device}"')
        mido_port.send(mido_msg)
    else:
        logger.warning(f'Unknown MIDI output in event {msg}')


def open_output_midi_devices():
    used_midi_outputs = set()

    for midi_device_control in yaml_namespace.find_by_class(MidiDeviceControl):
        if midi_device_control.midi_output is not None:
            used_midi_outputs.add(midi_device_control.midi_output)

    for midi_output in used_midi_outputs:
        logger.info(f'Open "{midi_output}" MIDI port...')

        mido_outputs[midi_output] = mido.open_output(midi_output)


def on_events_out(msg: DeviceControlEvent):
    logger.info(f"Send MIDI event {msg}")
    send_midi(msg)


def setup_output():
    for midi_device_control in yaml_namespace.find_by_class(MidiDeviceControl):
        if midi_device_control.midi_output is not None:
            logger.debug(f'Subscribe to "{midi_device_control.name}" events_out subject')
            midi_device_control.var_subjects['events_out'].subscribe(on_next=on_events_out)
