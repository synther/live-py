import logging
import pprint
from typing import Iterable, List, Optional, Tuple

import reactivex
import reactivex.abc
import reactivex.operators

from live_py.base import DeviceControlEvent

from . import device_control_events, yaml_namespace, yaml_pipelines
from .beat_scheduler import BeatScheduler, beats, ticks_per_beat
from .yaml_namespace import YamlObject


logger = logging.getLogger(__name__)


class WidgetControl(YamlObject):
    """Something able to receive Device Control Events
    """

    device_name: Optional[str]
    device_control_id: Optional[int]

    def __init__(self,
                 device_name: Optional[str],
                 device_control_id: Optional[int],
                 yaml_obj: dict):
        super().__init__(yaml_obj)
        self.device_name = device_name
        self.device_control_id = device_control_id

    def __str__(self) -> str:
        return f"WidgetControl(name={self.name}, class={self.yaml_class})"

    def map_device_control_event(self, event: DeviceControlEvent) -> Optional[Tuple]:
        pass


class Button(WidgetControl):
    def __init__(self, yaml_obj: dict):
        logger.debug(f'Create from {yaml_obj}')

        super().__init__(
            device_name=yaml_obj.get('device', None),
            device_control_id=yaml_obj.get('device_control_id', None),
            yaml_obj=yaml_obj,
        )

        # TODO address device controls by yaml namespace name, not by id

    def __repr__(self) -> str:
        return f'Button("{self.name}")'

    def map_device_control_event(self, event: DeviceControlEvent) -> Optional[Tuple]:
        match event:
            case device_control_events.MidiNoteOnDeviceControlEvent():
                return ((self.name, 'value'), 1)

            case device_control_events.MidiNoteOffDeviceControlEvent():
                return ((self.name, 'value'), 0)

            case device_control_events.MidiNoteDeviceControlEvent():
                return ((self.name, 'value'), min(1, event.velocity))

            case _:
                return None


class Page(YamlObject):
    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj, ['active'])

        widgets_iter = (yaml_namespace.new_obj(w) for w in yaml_obj['widgets'])
        widgets_iter = filter(lambda o: o is not None, widgets_iter)

        self.widgets = list(widgets_iter)

        for w in self.widgets:
            assert(isinstance(w, WidgetControl))


class Var(YamlObject):
    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj, ['value'])


class Clock(YamlObject):
    beat_scheduler: Optional[BeatScheduler] = None

    def __init__(self, yaml_obj: dict):
        beat_scheduler = Clock.beat_scheduler
        assert beat_scheduler is not None
        self._beat_scheduler = beat_scheduler
        super().__init__(yaml_obj, ['tempo', 'shuffle', '!clock_out', 'transport_out'])
        self._started_ticks: Optional[int] = None
        self._beats_in_measure = 4

        self.var_subjects['shuffle'].subscribe(
            on_next=lambda v: logger.info(f'Changing shuffle = {v}')
        )

        self.var_subjects['tempo'].subscribe(on_next=self.on_tempo)

    def on_tempo(self, tempo):
        logger.info(f'Tempo changed {tempo}')
        self._beat_scheduler.change_ticks_resolution_bpm(tempo)

    def start(self):
        logger.info(f'Clock "{self.name}" started')
        self._started_ticks = self._beat_scheduler.now

        reactivex.timer(
            duetime=0,
            period=ticks_per_beat / 24,
            scheduler=self._beat_scheduler
        ).subscribe(
            on_next=lambda x: self.var_subjects['clock_out'].on_next(
                device_control_events.MidiClockEvent(control=None, midi_device=None)
            )
        )

        reactivex.timer(
            duetime=0,
            period=ticks_per_beat,
            scheduler=self._beat_scheduler
        ).subscribe(
            on_next=lambda x: logger.debug('Beat Bar' if x % 4 == 0 else 'Beat')
        )

        self.var_subjects['transport_out'].on_next(
            device_control_events.MidiStartEvent(control=None, midi_device=None)
        )

    def stop(self):
        logger.info(f'Clock "{self.name}" stopped')
        self._started_ticks = None

    @property
    def transport_time(self) -> tuple[int, float]:
        """
        Musical time is (measure, beat)
        """

        if self._started_ticks is None:
            return (1, 1.0)

        now_beats = self.now_beats

        measures = int((now_beats - 1) // self._beats_in_measure) + 1
        beats = now_beats - self._beats_in_measure * (measures - 1)

        return (measures, beats)

    @property
    def now_beats(self) -> float:
        """
        Time in beats after transport is started
        """

        if self._started_ticks is None:
            return 1.0

        now_ticks = self._beat_scheduler.now
        now_beats = (now_ticks - self._started_ticks) / ticks_per_beat

        return now_beats


class Sequencer(YamlObject):
    beat_scheduler: Optional[BeatScheduler] = None

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj, [
            'events_in',
            'events_out',

            'record_exists',
            'recording_control',
            'playback_control',
            'is_recording',
            'is_playing',
        ])

        beat_scheduler = Sequencer.beat_scheduler
        assert beat_scheduler is not None
        self._beat_scheduler = beat_scheduler

        self.var_subjects['recording_control'].subscribe(
            on_next=self.on_recording_control
        )

        self.var_subjects['playback_control'].subscribe(
            on_next=self.on_playback_control
        )

        self.var_subjects['events_in'].subscribe(
            on_next=self.on_events_in
        )

        clock = yaml_namespace.get_obj('clock')
        assert isinstance(clock, Clock)
        self._clock = clock

        self._recording_started_beats: Optional[float] = None
        """Also an indication that recording is active"""

        self._record: list[tuple[float, DeviceControlEvent]] = []
        """Format: beat, event"""

        self._playing_subscription: Optional[reactivex.abc.DisposableBase] = None

    def on_recording_control(self, e):
        logger.info(f"on_recording_control, {e=}")

        if e == True:
            logger.info(f'Start recording on "{self.name}"')
            self._recording_started_beats = self._clock.now_beats
            self._record = []
            self.var_subjects['is_recording'].on_next(True)
            self.var_subjects['record_exists'].on_next(True)
        elif e == False:
            logger.info(
                f'Stop recording on "{self.name}". Recorded seq = {pprint.pformat(self._record)}')
            self._recording_started_beats = None
            self.var_subjects['is_recording'].on_next(False)

    def on_playback_control(self, e):
        logger.info(f"on_playback_control, {e=}")

        if e == True:
            logger.info(f'Start playback command on "{self.name}"...')
            self.var_subjects['is_playing'].on_next(True)

            if self._playing_subscription is not None:
                self._playing_subscription.dispose()

            now_ticks = self._beat_scheduler.now
            current_beat = now_ticks // ticks_per_beat
            quantized_beats = (current_beat // 4 + 1) * 4
            delay_ticks = quantized_beats * ticks_per_beat - now_ticks

            logger.debug(f'{now_ticks=}, {current_beat=}, {quantized_beats=}, {delay_ticks=}')

            def start_playback(scheduler: reactivex.abc.SchedulerBase, state):
                logger.info(f'Start playback quantized on "{self.name}"')

                self._playing_subscription = reactivex.from_list(self._record).pipe(
                    reactivex.operators.delay_with_mapper(
                        lambda e: reactivex.timer(beats(e[0])),
                    ),
                    reactivex.operators.do_action(
                        on_next=lambda e: logger.info(f'Sequencer out event: {e}')
                    )
                ).subscribe(
                    on_next=lambda e: self.var_subjects['events_out'].on_next(e[1]),
                    scheduler=self._beat_scheduler,
                )

            quantized_ticks = quantized_beats * ticks_per_beat
            self._beat_scheduler.schedule_absolute(quantized_beats * ticks_per_beat, start_playback)
            logger.debug(f'{now_ticks=} ({current_beat=}), {quantized_beats=} ({quantized_ticks=})')

            logger.info(f'Start playback command on "{self.name}"...done')

        elif e == False:
            logger.info(f'Stop playback on "{self.name}"')
            self.var_subjects['is_playing'].on_next(False)

            if self._playing_subscription is not None:
                self._playing_subscription.dispose()
                self._playing_subscription = None

    def on_events_in(self, e):
        logger.info(f"Seq: on_events_in, {e=}")

        if self._recording_started_beats is not None:
            rec = (self._clock.now_beats - self._recording_started_beats, e)

            logger.info(f"Record {rec} on {self.name}")

            self._record.append(rec)


def get_widgets_in_page(page: str) -> Iterable[WidgetControl]:
    widgets = yaml_namespace.get_obj(page).widgets
    return widgets


yaml_namespace.register_class('page', Page)
yaml_namespace.register_class('button', Button)
yaml_namespace.register_class('var', Var)
yaml_namespace.register_class('clock', Clock)
yaml_namespace.register_class('sequencer', Sequencer)
