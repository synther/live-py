import asyncio
import contextlib
from optparse import Option
import time
from dataclasses import dataclass
from functools import partial
from typing import Set, Optional, Tuple

import mido


@dataclass
class ClipNote:
    midi_msg: mido.Message
    note_time_in_clip_s: float


@dataclass
class IncomingMidi:
    midi_msg: mido.Message
    port: str


class Sequencer:
    def __init__(self) -> None:
        self.recording_starttime_s = 0
        self.notes: list[ClipNote] = []

    def start_recording(self):
        print('Start recording')
        self.recording_starttime_s = time.monotonic()
        self.notes = []

    def stop_recording(self):
        print('Stop recording')
        self.recording_starttime_s = 0

    def is_recording_started(self):
        return self.recording_starttime_s != 0

    def record_note(self, msg):
        assert self.recording_starttime_s != 0

        note = ClipNote(midi_msg=msg,
                        note_time_in_clip_s=time.monotonic() - self.recording_starttime_s)

        self.notes.append(note)

        print(f'Note recorded {note}')

    async def start_playback(self):
        print('Start playback')

        playback_starttime_s = time.monotonic()

        for note in self.notes:
            next_note_playback_time_s = note.note_time_in_clip_s + playback_starttime_s

            curr_time = time.monotonic()

            if next_note_playback_time_s > curr_time:
                sleep_time_s = next_note_playback_time_s - curr_time
                print(f'Sleeping for {sleep_time_s}')
                await asyncio.sleep(sleep_time_s)

            print(f'Sending note {note.midi_msg}')

            yield note.midi_msg


class Events:
    def __init__(self, incoming_midi_q: asyncio.Queue[IncomingMidi]) -> None:
        self._incoming_midi_q = incoming_midi_q
        self._midi_in_waiting_futures: Set[asyncio.Future] = set()

    async def wait_for_midi_in(self) -> IncomingMidi:
        """
        Block until you get a midi message from any port.
        """

        f = asyncio.get_running_loop().create_future()

        self._midi_in_waiting_futures.add(f)

        # print('wait for midi in...')

        return await f

    async def run(self):
        while True:
            incoming_midi = await self._incoming_midi_q.get()
            # print('incoming midi in events task')

            for f in self._midi_in_waiting_futures:
                f.set_result(incoming_midi)
                # print('notify some waiter')

            self._midi_in_waiting_futures.clear()


class MidiClock:
    resolution_ticks_per_beat = 24

    def __init__(self) -> None:
        self._last_tick_time_ns: Optional[int] = None
        self._last_tick_count: Optional[int] = None
        self._last_tick_bpm = 120
        self._tick_duration_ns: int = int(
            1000000000 * 60 / self._last_tick_bpm / MidiClock.resolution_ticks_per_beat)

    def start(self):
        self._last_tick_time_ns = time.monotonic_ns()
        self._last_tick_count = 0

    @property
    def bpm(self) -> float:
        return self._last_tick_bpm

    @property
    def curr_tick(self) -> Optional[Tuple[int, int]]:
        """
        Returns (tick count, tick ns time)
        """

        if self._last_tick_time_ns is None:
            return None

        if self._last_tick_count is None:
            return None

        curr_time_ns = time.monotonic_ns()
        ticks_passed = (curr_time_ns - self._last_tick_time_ns) // self._tick_duration_ns
        curr_tick_count = self._last_tick_count + ticks_passed
        curr_tick_time_ns = self._last_tick_time_ns + ticks_passed * self._tick_duration_ns

        return (curr_tick_count, curr_tick_time_ns)

    def stop(self):
        self._last_tick_time_ns = None
        self._last_tick_count = None

    def set_tempo_bpm(self, bpm: float):
        print(f'Set BPM to {bpm}')

        curr_tick = self.curr_tick

        if curr_tick is not None:
            self._last_tick_count, self._last_tick_time_ns = curr_tick

        self._last_tick_bpm = bpm
        self._tick_duration_ns = int(1000000000 * 60 / bpm / MidiClock.resolution_ticks_per_beat)
        # TODO invalidate all sleeps

    async def wait_for_tick(self, tick: int):
        # TODO what to do when clock is stopped?
        assert self._last_tick_count is not None
        assert self._last_tick_time_ns is not None

        if tick <= self._last_tick_count:
            # TODO last tick is not current tick
            return

        wait_ns = (tick - self._last_tick_count) * self._tick_duration_ns + \
            self._last_tick_time_ns - time.monotonic_ns()
        wait_s = wait_ns / 1000000000

        print(
            f'Wait for {wait_s * 1000} ms for the {tick} tick (resolution = {MidiClock.resolution_ticks_per_beat} ticks per beat)')

        await asyncio.sleep(wait_s)


async def clock_generator(output_port, midi_clock: MidiClock):
    midi_clock.start()

    last_tick_sent: Optional[int] = None

    while True:
        if last_tick_sent is None:
            curr_tick = midi_clock.curr_tick

            # TODO what to do when clock is stopped?
            assert curr_tick is not None

            tick_to_send, _ = curr_tick
        else:
            tick_to_send = last_tick_sent + 1

        await midi_clock.wait_for_tick(tick_to_send)
        print('output clock')
        output_port.send(mido.Message('clock'))

        last_tick_sent = tick_to_send


async def tempo_controller(events: Events, midi_clock: MidiClock):
    while True:
        incoming_midi = await events.wait_for_midi_in()

        if incoming_midi.port != 'Launchpad Pro Standalone Port':
            continue

        if incoming_midi.midi_msg.type == 'control_change' and \
            incoming_midi.midi_msg.control == 70 and \
                incoming_midi.midi_msg.value == 127:
            print(f'Increase BPM')

            midi_clock.set_tempo_bpm(midi_clock.bpm + 5)


async def note_generator(output_port):
    while True:
        print('output note')
        output_port.send(mido.Message('note_on', channel=0, note=57, velocity=90))
        await asyncio.sleep(0.5)
        output_port.send(mido.Message('note_off', channel=0, note=57, velocity=64))

        await asyncio.sleep(0.5)


async def monitoring_generator(events: Events, output_synth_port):
    while True:
        incoming_midi = await events.wait_for_midi_in()

        if incoming_midi.port != 'Arturia KeyStep 32':
            continue

        if incoming_midi.midi_msg.type == 'note_on' or incoming_midi.midi_msg.type == 'note_off':
            print(f'monitoring sending {incoming_midi}')

            output_synth_port.send(incoming_midi.midi_msg)


async def sequencer_generator(events: Events, output_synth_port):
    sequencer = Sequencer()

    while True:
        incoming_midi = await events.wait_for_midi_in()

        if incoming_midi.port == 'Launchpad Pro Standalone Port' and \
                incoming_midi.midi_msg.type == 'note_on' and \
                incoming_midi.midi_msg.note == 81 and \
                incoming_midi.midi_msg.velocity > 0:

            if sequencer.is_recording_started():
                sequencer.stop_recording()

                async for midi_msg in sequencer.start_playback():
                    output_synth_port.send(midi_msg)

            else:
                sequencer.start_recording()

        if incoming_midi.port == 'Arturia KeyStep 32':
            if sequencer.is_recording_started():
                sequencer.record_note(incoming_midi.midi_msg)


async def run_generators():
    try:
        incoming_midi_q: asyncio.Queue[IncomingMidi] = asyncio.Queue()

        with contextlib.ExitStack() as stack:
            output_synth_port = mido.open_output(
                'Neutron(1)',
                callback=partial(on_input_midi,
                                 port='Neutron(1)',
                                 output_synth_port=None,
                                 asyncio_loop=asyncio.get_running_loop(),
                                 incoming_midi_q=incoming_midi_q,
                                 ))

            input_controller_port = mido.open_input(
                'Launchpad Pro Standalone Port',
                callback=partial(on_input_midi,
                                 port='Launchpad Pro Standalone Port',
                                 output_synth_port=output_synth_port,
                                 asyncio_loop=asyncio.get_running_loop(),
                                 incoming_midi_q=incoming_midi_q,
                                 ))

            input_keyboard_port = mido.open_input(
                'Arturia KeyStep 32',
                callback=partial(on_input_midi,
                                 port='Arturia KeyStep 32',
                                 output_synth_port=output_synth_port,
                                 asyncio_loop=asyncio.get_running_loop(),
                                 incoming_midi_q=incoming_midi_q,
                                 ))

            input_sync_port = mido.open_input(
                'TR-6S',
                callback=partial(on_input_midi,
                                 port='TR-6S',
                                 output_synth_port=None,
                                 asyncio_loop=asyncio.get_running_loop(),
                                 incoming_midi_q=incoming_midi_q,
                                 ))

            stack.enter_context(input_controller_port)
            stack.enter_context(input_keyboard_port)
            stack.enter_context(input_sync_port)
            stack.enter_context(output_synth_port)

            events = Events(incoming_midi_q=incoming_midi_q)
            midi_clock = MidiClock()

            tasks = [
                asyncio.create_task(note_generator(output_synth_port)),
                asyncio.create_task(monitoring_generator(events, output_synth_port)),
                asyncio.create_task(sequencer_generator(events, output_synth_port)),
                asyncio.create_task(clock_generator(output_synth_port, midi_clock)),
                asyncio.create_task(tempo_controller(events, midi_clock)),
                asyncio.create_task(events.run()),
            ]

            # TODO proper exit and cancellation
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    except KeyboardInterrupt:
        print('interrupted')


def on_input_midi(msg, port: str, output_synth_port, asyncio_loop, incoming_midi_q):
    # print(msg, port)

    asyncio_loop.call_soon_threadsafe(incoming_midi_q.put_nowait,
                                      IncomingMidi(midi_msg=msg, port=port))


if __name__ == '__main__':
    print(mido.get_input_names())

    asyncio.run(run_generators())


# ['Launchpad Pro Live Port', 'Launchpad Pro Standalone Port', 'Launchpad Pro MIDI Port',
#  'Neutron(1)', 'PS60 KEYBOARD', 'Arturia KeyStep 32', 'TR-6S', 'TR-6S CTRL',
#  'Launchpad Pro Live Port', 'Launchpad Pro Standalone Port', 'Launchpad Pro MIDI Port',
#  'Neutron(1)', 'Arturia KeyStep 32', 'TR-6S', 'TR-6S CTRL']
