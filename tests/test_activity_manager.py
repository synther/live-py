import logging

import reactivex
import reactivex.operators

from live_py import (yaml_device_controls, yaml_namespace)
from live_py.activity_manager import activity_manager
from live_py.device_control_events import MidiNoteOnDeviceControlEvent

logger = logging.getLogger(__name__)


def test_not_visible_0():
    yaml_namespace.new_obj({
        "page": "main",
        "active": True,
        "widgets": [
            {"button": "shift_inc", "device": "Surface", "device_control": 1},
        ],
    })

    control = yaml_device_controls.MidiNoteOffDeviceControl(
        device_name='Surface',
        control_id=1,
        midi_input='Surface Midi In',
        midi_channel=1,
        midi_note=10,
    )

    results = []

    in_events = [
        MidiNoteOnDeviceControlEvent(control=control, velocity=127),
    ]

    reactivex.from_iterable(
        in_events
    ).pipe(
        activity_manager()
    ).subscribe(
        on_next=results.append
    )

    assert [

    ] == results


def test_not_visible_1():
    yaml_namespace.new_obj({
        "page": "main",
        "active": True,
        "widgets": [
            {"button": "shift_inc", "device": "Surface", "device_control": 1},
        ],
    })

    control = yaml_device_controls.MidiNoteOffDeviceControl(
        device_name='Surface',
        control_id=1,
        midi_input='Surface Midi In',
        midi_channel=1,
        midi_note=10,
    )

    results = []

    in_events = [
        (('main', 'active'), True),
        (('main', 'active'), True),
        MidiNoteOnDeviceControlEvent(control=control, velocity=100),
        (('main', 'active'), False),
        MidiNoteOnDeviceControlEvent(control=control, velocity=101),
    ]

    reactivex.from_iterable(
        in_events
    ).pipe(
        activity_manager()
    ).subscribe(
        on_next=results.append
    )

    assert [
        (MidiNoteOnDeviceControlEvent(control=control, velocity=100), yaml_namespace.get_obj('shift_inc')),
    ] == results


def test_not_active_twice():
    yaml_namespace.new_obj({
        "page": "main",
        "active": True,
        "widgets": [
            {"button": "shift_inc", "device": "Surface", "device_control": 1},
        ],
    })

    control = yaml_device_controls.MidiNoteOffDeviceControl(
        device_name='Surface',
        control_id=1,
        midi_input='Surface Midi In',
        midi_channel=1,
        midi_note=10,
    )

    results = []

    in_events = [
        (('main', 'active'), True),
        MidiNoteOnDeviceControlEvent(control=control, velocity=100),
        (('main', 'active'), False),
        (('main', 'active'), False),
        MidiNoteOnDeviceControlEvent(control=control, velocity=101),
        (('main', 'active'), True),
        MidiNoteOnDeviceControlEvent(control=control, velocity=102),
    ]

    reactivex.from_iterable(
        in_events
    ).pipe(
        activity_manager(),
        reactivex.operators.do_action(
            on_next=lambda v: logger.debug(f"Out from Activity Manager: {v}"))
    ).subscribe(
        on_next=results.append
    )

    assert [
        (MidiNoteOnDeviceControlEvent(control=control, velocity=100), yaml_namespace.get_obj('shift_inc')),
        (MidiNoteOnDeviceControlEvent(control=control, velocity=102), yaml_namespace.get_obj('shift_inc')),
    ] == results


def test_happy_path():
    yaml_namespace.new_obj({
        "page": "main",
        "active": True,
        "widgets": [
            {"button": "shift_inc", "device": "Surface", "device_control": 1},
        ],
    })

    control = yaml_device_controls.MidiNoteOffDeviceControl(
        device_name='Surface',
        control_id=1,
        midi_input='Surface Midi In',
        midi_channel=1,
        midi_note=10,
    )

    results = []

    in_events = [
        (('main', 'active'), True),
        MidiNoteOnDeviceControlEvent(control=control, velocity=127),
    ]

    reactivex.from_iterable(
        in_events
    ).pipe(
        activity_manager()
    ).subscribe(
        on_next=results.append
    )

    assert [
        (MidiNoteOnDeviceControlEvent(control=control, velocity=127), yaml_namespace.get_obj('shift_inc')),
    ] == results


def test_2_pages_overlapp():
    yaml_namespace.new_obj({
        "page": "main",
        "active": True,
        "widgets": [
            {"button": "start", "device": "Surface", "device_control": 1},
        ],
    })

    yaml_namespace.new_obj({
        "page": "settings",
        "active": False,
        "widgets": [
            {"button": "tempo", "device": "Surface", "device_control": 1},
        ],
    })

    control = yaml_device_controls.MidiNoteOffDeviceControl(
        device_name='Surface',
        control_id=1,
        midi_input='Surface Midi In',
        midi_channel=1,
        midi_note=10,
    )

    results = []

    in_events = [
        (('main', 'active'), True),
        MidiNoteOnDeviceControlEvent(control=control, velocity=100),
        (('main', 'active'), False),
        (('main', 'active'), False),
        MidiNoteOnDeviceControlEvent(control=control, velocity=101),
        (('settings', 'active'), True),
        MidiNoteOnDeviceControlEvent(control=control, velocity=102),
    ]

    reactivex.from_iterable(
        in_events
    ).pipe(
        activity_manager(),
        reactivex.operators.do_action(
            on_next=lambda v: logger.debug(f"Out from Activity Manager: {v}"))
    ).subscribe(
        on_next=results.append
    )

    assert [
        (MidiNoteOnDeviceControlEvent(control=control, velocity=100), yaml_namespace.get_obj('start')),
        (MidiNoteOnDeviceControlEvent(control=control, velocity=102), yaml_namespace.get_obj('tempo')),
    ] == results
