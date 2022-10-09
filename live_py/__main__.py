import asyncio
import contextlib
import time
from dataclasses import dataclass
from functools import partial
from typing import Set, Optional, Tuple

import mido


@dataclass
class ClipNote:
    midi_msg: mido.Message

    """clip_tick == 0 on the clip start
    """
    clip_tick: int


@dataclass
class IncomingMidi:
    midi_msg: mido.Message
    port: str

class Control:
    type_name = "base"

    def __init__(self, name: str) -> None:
        pass

    def trigger(self, value):
        pass


class Button(Control):
    type_name = "Button"

class Grid(Control):
    type_name = "Grid"

class Layout:
    def place_control(self, control, position):
        """
        position is control number, range of controls, lower and upper corners. Depends on control
        """
        pass

    def trigger_control(self, postion_n, value):
        pass


class MidiClock:
    resolution_ticks_per_beat = 24

    def __init__(self) -> None:
        """
        The "last" tick is when tempo changed the last time
        """
        self._last_tick_time_ns: Optional[int] = None
        self._last_tick_count: Optional[int] = None
        self._last_tick_bpm = 120
        self._tick_duration_ns: int = int(
            1000000000 * 60 / self._last_tick_bpm / MidiClock.resolution_ticks_per_beat)

        self._tick_waiters: Set[asyncio.Task] = set()

    def start(self):
        self._last_tick_time_ns = time.monotonic_ns()
        self._last_tick_count = 0

    @property
    def bpm(self) -> float:
        return self._last_tick_bpm

    @property
    def curr_tick(self) -> Tuple[int, int]:
        """
        Returns (tick count, tick ns time)
        """

        if self._last_tick_time_ns is None:
            raise RuntimeError('Clock is not started')

        if self._last_tick_count is None:
            raise RuntimeError('Clock is not started')

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

        for waiting_task in self._tick_waiters:
            waiting_task.cancel()

    async def wait_for_tick(self, tick: int):
        # TODO what to do when clock is stopped?
        assert self._last_tick_count is not None
        assert self._last_tick_time_ns is not None

        while True:
            try:
                if tick <= self.curr_tick[0]:
                    return

                wait_ns = (tick - self._last_tick_count) * self._tick_duration_ns + \
                    self._last_tick_time_ns - time.monotonic_ns()
                wait_s = wait_ns / 1000000000

                print(
                    f'Wait for {wait_s * 1000} ms for the {tick} tick (resolution = {MidiClock.resolution_ticks_per_beat} ticks per beat)')

                sleep_task = asyncio.create_task(asyncio.sleep(wait_s))

                try:
                    self._tick_waiters.add(sleep_task)
                    await sleep_task
                finally:
                    self._tick_waiters.remove(sleep_task)
            except asyncio.CancelledError:
                print('Wait is no longer valid. Reschedule it')

                # TODO tempo reschedule case vs actual cancellation

                continue


class Sequencer:
    def __init__(self, clock: MidiClock) -> None:
        self.recording_starttick: int = 0
        self.notes: list[ClipNote] = []
        self.clock: MidiClock = clock

    def start_recording(self):
        print('Start recording')
        self.recording_starttick, _ = self.clock.curr_tick
        self.notes = []

    def stop_recording(self):
        print('Stop recording')
        self.recording_starttick = 0

    def is_recording_started(self):
        return self.recording_starttick != 0

    def record_note(self, msg):
        assert self.recording_starttick != 0

        note = ClipNote(midi_msg=msg,
                        clip_tick=self.clock.curr_tick[0] - self.recording_starttick)

        self.notes.append(note)

        print(f'Note recorded {note}')

    async def start_playback(self):
        print('Start playback')

        playback_starttick, _ = self.clock.curr_tick

        for note in self.notes:
            next_note_tick = playback_starttick + note.clip_tick
            await self.clock.wait_for_tick(next_note_tick)
            print(f'Sending note {note.midi_msg}')
            yield note.midi_msg


class Events:
    def __init__(self, incoming_midi_q) -> None:
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
            print(f'Decrease BPM')

            midi_clock.set_tempo_bpm(midi_clock.bpm - 10)


async def note_generator(output_port):
    while True:
        print('output note')
        output_port.send(mido.Message('note_on', channel=0, note=62, velocity=90))
        await asyncio.sleep(0.5)
        output_port.send(mido.Message('note_off', channel=0, note=62, velocity=64))

        await asyncio.sleep(0.5)


async def monitoring_generator(events: Events, output_synth_port):
    while True:
        incoming_midi = await events.wait_for_midi_in()

        if incoming_midi.port != 'Arturia KeyStep 32':
            continue

        if incoming_midi.midi_msg.type == 'note_on' or incoming_midi.midi_msg.type == 'note_off':
            print(f'monitoring sending {incoming_midi}')

            output_synth_port.send(incoming_midi.midi_msg)


async def sequencer_generator(events: Events, clock: MidiClock, output_synth_port):
    # TODO use another clock (not MidiClock) with a higher resolution
    sequencer = Sequencer(clock)

    while True:
        incoming_midi = await events.wait_for_midi_in()

        if incoming_midi.port == 'Launchpad Pro Standalone Port' and \
                incoming_midi.midi_msg.type == 'note_on' and \
                incoming_midi.midi_msg.note == 81 and \
                incoming_midi.midi_msg.velocity > 0:

            if sequencer.is_recording_started():
                # TODO if note is on, off it forcibly
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
                # asyncio.create_task(note_generator(output_synth_port)),
                asyncio.create_task(monitoring_generator(events, output_synth_port)),
                asyncio.create_task(sequencer_generator(events, midi_clock, output_synth_port)),
                asyncio.create_task(clock_generator(output_synth_port, midi_clock)),
                asyncio.create_task(tempo_controller(events, midi_clock)),
                asyncio.create_task(events.run()),
            ]

            # TODO catch exceptions from tasks
            # TODO proper exit and cancellation
            await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print('interrupted')


def on_input_midi(msg, port: str, output_synth_port, asyncio_loop, incoming_midi_q):
    # print(msg, port)

    # if msg.type != 'note_on' and msg.type != 'note_off':
    #     return

    asyncio_loop.call_soon_threadsafe(incoming_midi_q.put_nowait,
                                      IncomingMidi(midi_msg=msg, port=port))


if __name__ == '__main__':
    print(mido.get_input_names())

    asyncio.run(run_generators(), debug=True)


# ['Launchpad Pro Live Port', 'Launchpad Pro Standalone Port', 'Launchpad Pro MIDI Port',
#  'Neutron(1)', 'PS60 KEYBOARD', 'Arturia KeyStep 32', 'TR-6S', 'TR-6S CTRL',
#  'Launchpad Pro Live Port', 'Launchpad Pro Standalone Port', 'Launchpad Pro MIDI Port',
#  'Neutron(1)', 'Arturia KeyStep 32', 'TR-6S', 'TR-6S CTRL']


# Arturia KeyStep 32:Arturia KeyStep 32 MIDI 1 24:0
# Arturia KeyStep 32:Arturia KeyStep 32 MIDI 1 24:0
# Launchpad Pro:Launchpad Pro MIDI 1 20:0
# Launchpad Pro:Launchpad Pro MIDI 1 20:0
# Launchpad Pro:Launchpad Pro MIDI 2 20:1
# Launchpad Pro:Launchpad Pro MIDI 2 20:1
# Launchpad Pro:Launchpad Pro MIDI 3 20:2
# Launchpad Pro:Launchpad Pro MIDI 3 20:2
# Midi Through:Midi Through Port-0 14:0
# Midi Through:Midi Through Port-0 14:0
# Neutron(1):Neutron(1) MIDI 1 16:0
# Neutron(1):Neutron(1) MIDI 1 16:0
# PS60:PS60 MIDI 1 28:0
# PS60:PS60 MIDI 1 28:0
# TR-6S:TR-6S MIDI 1 32:0
# TR-6S:TR-6S MIDI 1 32:0
# TR-6S:TR-6S MIDI 2 32:1
# TR-6S:TR-6S MIDI 2 32:1
