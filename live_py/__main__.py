import logging
import pprint
import time

import coloredlogs
import mido
import yaml
from reactivex import Subject
from reactivex import operators as ops
import reactivex

from . import (yaml_device_controls, yaml_devices, yaml_namespace,
               yaml_pipelines)
from .base import DeviceControlEvent
from .yaml_elements import WidgetControl
from .activity_manager import activity_manager

pp = pprint.PrettyPrinter(indent=4)


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

coloredlogs.install(level='DEBUG',
                    fmt='%(asctime)s,%(msecs)03d %(name)22s %(levelname)5s %(message)s')


def route_to_var(msg):
    var_subject = yaml_pipelines.get_var_subject(msg[0])

    if var_subject is not None:
        logger.debug(f'route {msg[1]} to {msg[0]}')
        var_subject.on_next(msg[1])

# def device_control_event_to_widget_event(device_control_event: DeviceControlEvent,
#                                          widget: WidgetControl):
#     widget_event = widget.map_device_control_event(device_control_event)

#     if widget_event:
#         reactivex.just()

with open('set-pipelines.yaml', 'r') as stream:
    yaml_data = yaml.safe_load(stream)

    for yaml_obj in yaml_data:
        if next(iter(yaml_obj)) == 'device':
            yaml_devices.create_device(yaml_obj)

    for yaml_obj in yaml_data:
        yaml_namespace.new_obj(yaml_obj)

    for yaml_obj in yaml_data:
        if next(iter(yaml_obj)) == 'pipeline':
            yaml_pipelines.create_pipeline(yaml_obj)


midi_in_subj = Subject()

print(mido.get_input_names())


def on_midi_in(msg):
    logger.debug(f"midi msg: {msg}")

    if msg.type in ('note_on', 'note_off'):
        midi_in_subj.on_next(msg)


def midi_in_to_device_event(midi_msg):
    if midi_msg.type in ('note_on', 'note_off'):
        for control in yaml_devices.get_controls('Launch Control'):
            if isinstance(control, yaml_device_controls.MidiNoteDeviceControl) and \
                    control.midi_input == 'Launch Control' and \
                control.midi_channel == midi_msg.channel and \
                    control.midi_note == midi_msg.note:

                m = control.midi_to_device_event(midi_msg)

                logger.debug(f"Found device control: {m}")

                # TODO one control id - multiple DeviceControls

                # TODO return multiple device events
                # TODO return none device events

                return m

    logger.debug(f"Not found device control, {midi_msg=}")

    return ('dummy', 'Device', 0, 0)


input_midi_port = mido.open_input('Launch Control', callback=on_midi_in)

# TODO send ('active', 'main', True) first to Activity Manager

print(input_midi_port)

# midi_in = reactivex.of(
#     ('active', 'main', True),
#     ('midicc', 'LaunchPad1', 1, 127),  # tempo dec
#     ('midicc', 'LaunchPad1', 1, 0),
#     ('midicc', 'LaunchPad1', 2, 127),  # tempo inc
#     ('midicc', 'LaunchPad1', 2, 0),
#     ('midicc', 'LaunchPad1', 3, 127),  # shift x10 pressed
#     ('midicc', 'LaunchPad1', 1, 127),  # tempo dec
#     ('midicc', 'LaunchPad1', 1, 0),
#     ('midicc', 'LaunchPad1', 1, 127),  # tempo dec
#     ('midicc', 'LaunchPad1', 1, 0),
#     ('midicc', 'LaunchPad1', 2, 127),  # tempo inc
#     ('midicc', 'LaunchPad1', 2, 0),
#     ('midicc', 'LaunchPad1', 3, 0),  # shift x10 released
#     ('midicc', 'LaunchPad1', 2, 127),  # tempo inc
#     ('midicc', 'LaunchPad1', 2, 0),
#     # ('active', 'shuffle', True),

#     # ('midicc', 'LaunchPad1', 2, 127),
#     # ('midicc', 'LaunchPad1', 2, 0),

#     # ('active', 'shuffle', False),

#     # ('midicc', 'LaunchPad1', 2, 127),
#     # ('midicc', 'LaunchPad1', 2, 0),

#     # ('midicc', 'LaunchPad2', 2, 0),
#     # ('midicc', 'LaunchPad2', 2, 0),
#     # ('midicc', 'LaunchPad2', 1, 0),
# )

midi_in = midi_in_subj.pipe(
    ops.map(midi_in_to_device_event)
)

midi_in.pipe(
    ops.merge(
        yaml_pipelines.get_var_subject(('main', 'active')).pipe(
            ops.map(lambda v: (('main', 'active'), v))
        )
    ),
    activity_manager(),
    ops.do_action(
        on_next=lambda v: logger.debug(f'Activity Manager out: {v}'),
        on_completed=lambda: logger.debug(f'Activity Manager on_completed')
    ),
    ops.starmap(lambda ev, widget: widget.map_device_control_event(ev)),
    ops.filter(lambda ev: ev is not None),
    ops.do_action(
        on_next=route_to_var
    ),
).subscribe()

for pipeline in yaml_pipelines.pipelines:
    pipeline.obs.subscribe(
        on_next=lambda v, pipe=pipeline.repr: logger.debug(f'pipeline {pipe} on_next: {v}'),
        on_completed=lambda: logger.debug(f'pipeline on_completed'),
        on_error=lambda e: logger.debug(f'pipeline error {e}'))

time.sleep(100)
