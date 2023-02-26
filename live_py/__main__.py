import logging
import pprint
import signal
from contextlib import ExitStack
from functools import partial
from threading import Event
from typing import List

import coloredlogs
import mido
import reactivex
import yaml
from reactivex import Subject
from reactivex import operators as ops

from live_py import (yaml_device_controls, yaml_devices, yaml_elements,
                     yaml_namespace, yaml_pipelines)
from live_py.activity_manager import activity_manager

from .beat_scheduler import BeatScheduler

pp = pprint.PrettyPrinter(indent=4)

# TODO add on_error on every .subscribe()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

coloredlogs.install(level='DEBUG',
                    fmt='%(asctime)s,%(msecs)03d %(name)22s %(levelname)5s %(message)s')


def route_to_var(msg):
    logger.debug(f"Trying to route {msg} to some subject")

    var_subject = yaml_pipelines.get_var_subject(msg[0])

    if var_subject is not None:
        logger.debug(f'Route {msg[1]} to {msg[0]}')
        var_subject.on_next(msg[1])


def load_yaml(yaml_path: str):
    with open(yaml_path, 'r') as stream:
        yaml_data = yaml.safe_load(stream)

        for yaml_obj in yaml_data:
            yaml_namespace.new_obj(yaml_obj)

        for yaml_obj in yaml_data:
            if next(iter(yaml_obj)) == 'pipeline':
                yaml_pipelines.create_pipeline(yaml_obj)


def on_midi_in(msg, device_name):
    logger.debug(f'mido msg from "{device_name}: {msg}')

    if msg.type in ('note_on', 'note_off'):
        midi_in_subj.on_next((device_name, msg))


def midi_in_to_device_event(device_name, mido_msg):
    device_control_events = [
        control.midi_to_device_event(mido_msg, device_name) for control in yaml_devices.find_controls_by_mido_msg(
            device_name, mido_msg
        )
    ]

    logger.debug(f"Converted device control events, {mido_msg=}, {device_control_events=}")

    return reactivex.from_list(device_control_events)


def get_page_active_subjects():
    obs: List[reactivex.Observable] = []

    for obj in yaml_namespace.find_by_class(yaml_elements.Page):
        obj_name = obj.name
        logger.debug(f"Will listen to {obj_name}.active subject")

        obs.append(
            obj.var_subjects['active'].pipe(
                ops.map(lambda v, obj_name=obj_name: ((obj_name, 'active'), v))
            )
        )

    return obs


beat_scheduler = BeatScheduler()
yaml_elements.Clock.beat_scheduler = beat_scheduler
yaml_elements.Sequencer.beat_scheduler = beat_scheduler
load_yaml('set.yaml')
midi_in_subj = Subject()
logger.info(f'MIDI inputs: {mido.get_input_names()}')

with ExitStack() as open_mido_devices:
    for midi_input in yaml_devices.find_midi_inputs():
        logger.debug(f'Open midi device "{midi_input}"...')

        open_mido_devices.enter_context(
            mido.open_input(
                midi_input,
                callback=partial(on_midi_in, device_name=midi_input),
            )
        )

        logger.info(f'Open "{midi_input}" MIDI port')

    yaml_device_controls.open_output_midi_devices()

    # TODO close opened output ports

    midi_in_subj.pipe(
        ops.starmap(midi_in_to_device_event),
        ops.merge_all(),
        ops.filter(lambda e: e is not None),
        ops.do_action(
            on_next=lambda e: yaml_device_controls.publish_event_to_subject(e),
        ),
    ).pipe(
        ops.merge(*get_page_active_subjects()),
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

    yaml_namespace.get_obj('clock').start()

    yaml_device_controls.setup_output()

    for pipeline in yaml_pipelines.pipelines:
        pipeline.obs.subscribe(
            # on_next=lambda v, pipe=pipeline.repr: logger.debug(f'pipeline {pipe} on_next: {v}'),
            on_completed=lambda pipe=pipeline.repr: logger.debug(f'pipeline {pipe} on_completed'),
            on_error=lambda e: logger.error(f'Pipeline error {e}'))

    def signal_handler(signal_number, frame):
        quit_event.set()

    quit_event = Event()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    quit_event.wait()

    logger.info("Exit")
