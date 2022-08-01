import dataclasses
import mido
import contextlib
import threading
import time
from functools import partial
import queue
from typing import Any
from dataclasses import dataclass


@dataclass
class ClipNote:
    midi_msg: Any
    note_time_in_clip_s: float


@dataclass
class PlaybackTask:
    notes: list[ClipNote]
    playback_starttime_s: float


class Sequencer:
    def __init__(self) -> None:
        self.recording_starttime_s = 0
        self.notes: list[ClipNote] = []

    def start_recording(self):
        print('Start recording')
        self.recording_starttime_s = time.time()
        self.notes = []

    def stop_recording(self):
        print('Stop recording')
        self.recording_starttime_s = 0

    def is_recording_started(self):
        return self.recording_starttime_s != 0

    def record_note(self, msg):
        assert self.recording_starttime_s != 0

        note = ClipNote(midi_msg=msg,
                        note_time_in_clip_s=time.time() - self.recording_starttime_s)

        self.notes.append(note)

        print(f'Note recorded {note}')

    def start_playback(self) -> PlaybackTask:
        print('Start playback')

        playback_starttime_s = time.time()

        playback_notes: list[ClipNote] = []

        for recorded in self.notes:
            # playback_time_s = playback_starttime_s + recorded.note_time_in_clip_s - recorded.clip_starttime_s
            playback_note = dataclasses.replace(recorded)
            playback_notes.append(playback_note)

        return PlaybackTask(notes=playback_notes,
                            playback_starttime_s=playback_starttime_s)


sequencer = Sequencer()
playback_q: queue.Queue[PlaybackTask] = queue.Queue()


def on_input_midi(msg, port: str, output_synth_port):
    print(msg, port)

    if port == 'Launchpad Pro Standalone Port' and msg.note == 81 and msg.type == 'note_on' and msg.velocity > 0:
        if sequencer.is_recording_started():
            sequencer.stop_recording()

            notes = sequencer.start_playback()
            playback_q.put_nowait(notes)
        else:
            sequencer.start_recording()

    elif port == 'Arturia KeyStep 32':
        if sequencer.is_recording_started():
            sequencer.record_note(msg)

        output_synth_port.send(msg)


def sending_task(stop_event, output_synth_port):
    while not stop_event.is_set():
        try:
            playback_task = playback_q.get(timeout=0.1)

            for note in playback_task.notes:
                next_note_playback_time_s = note.note_time_in_clip_s + playback_task.playback_starttime_s

                curr_time = time.time()

                if next_note_playback_time_s > curr_time:
                    sleep_time_s = next_note_playback_time_s - curr_time
                    print(f'Sleeping for {sleep_time_s}')
                    time.sleep(sleep_time_s)

                print(f'Sending note {note.midi_msg}')

                output_synth_port.send(note.midi_msg)

        except (queue.Full, queue.Empty):
            pass


if __name__ == '__main__':
    print(mido.get_input_names())

    sending_thread_stop_event = threading.Event()

    try:
        with contextlib.ExitStack() as stack:
            output_synth_port = mido.open_output(
                'Neutron(1)',
                callback=partial(on_input_midi,
                                 port='Neutron(1)',
                                 output_synth_port=None))

            input_controller_port = mido.open_input(
                'Launchpad Pro Standalone Port',
                callback=partial(on_input_midi,
                                 port='Launchpad Pro Standalone Port',
                                 output_synth_port=output_synth_port))

            input_keyboard_port = mido.open_input(
                'Arturia KeyStep 32',
                callback=partial(on_input_midi,
                                 port='Arturia KeyStep 32',
                                 output_synth_port=output_synth_port))

            sending_thread = threading.Thread(target=sending_task, args=(
                sending_thread_stop_event, output_synth_port))

            sending_thread.start()

            stack.enter_context(input_controller_port)
            stack.enter_context(input_keyboard_port)
            stack.enter_context(output_synth_port)

            time.sleep(1000)
    except KeyboardInterrupt:
        print('interrupted')

    sending_thread_stop_event.set()
    sending_thread.join()

# ['Launchpad Pro Live Port', 'Launchpad Pro Standalone Port', 'Launchpad Pro MIDI Port',
#  'Neutron(1)', 'PS60 KEYBOARD', 'Arturia KeyStep 32', 'Launchpad Pro Live Port',
#  'Launchpad Pro Standalone Port', 'Launchpad Pro MIDI Port', 'Neutron(1)', 'Arturia KeyStep 32']
