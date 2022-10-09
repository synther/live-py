from cProfile import label
from dataclasses import dataclass
from venv import create
import reactivex
import reactivex.operators
import asyncio
import typing
import collections.abc
import abc
from reactivex.scheduler.eventloop import AsyncIOScheduler

# def _lowercase(source):
#     def subscribe(observer, scheduler = None):
#         def on_next(value):
#             observer.on_next(value.lower())

#         return source.subscribe(
#             on_next,
#             observer.on_error,
#             observer.on_completed,
#             scheduler=scheduler)
#     return reactivex.create(subscribe)

# reactivex.of("Alpha", "Beta", "Gamma", "Delta", "Epsilon").pipe(
#         _lowercase
#      ).subscribe(lambda value: print("Received {0}".format(value)))


@dataclass
class Selected:
    selected: int = 0


def create_next_track_button():
    async def gen_events(observer):
        observer.on_next(1)
        await asyncio.sleep(0.5)
        observer.on_next(2)
        await asyncio.sleep(0.5)
        observer.on_completed()

    def on_subscribe(observer, scheduler):
        asyncio.create_task(gen_events(observer))

    return reactivex.create(on_subscribe)


def create_prev_track_button():
    async def gen_events(observer):
        observer.on_next(None)
        await asyncio.sleep(0.2)
        observer.on_next(None)
        await asyncio.sleep(0.2)
        observer.on_next(None)
        await asyncio.sleep(0.2)
        observer.on_next(None)
        await asyncio.sleep(0.2)
        observer.on_next(None)
        await asyncio.sleep(0.2)
        observer.on_completed()

    def on_subscribe(observer, scheduler):
        asyncio.create_task(gen_events(observer))

    return reactivex.create(on_subscribe)


def create_inc_selected_track(selected: Selected):
    def inc_selected_track(prev_observable):
        def on_subscribe(observer, scheduler):
            def on_next(v):
                selected.selected = selected.selected + 1
                observer.on_next(selected.selected)

            return prev_observable.subscribe(
                on_next=on_next
            )

        return reactivex.create(on_subscribe)

    return inc_selected_track


def create_dec_selected_track(selected: Selected):
    def dec_selected_track(prev_observable):
        def on_subscribe(observer, scheduler):
            def on_next(v):
                selected.selected = selected.selected - 1
                observer.on_next(selected.selected)

            return prev_observable.subscribe(
                on_next=on_next
            )

        return reactivex.create(on_subscribe)

    return dec_selected_track


class Lcd(reactivex.Observer):
    def on_next(self, value) -> None:
        print(f'LCD TEMPO: {value}')


class Device:
    def __init__(self) -> None:
        self.controls: dict[int, 'Control'] = {}


class Control:
    def __init__(self, device: Device) -> None:
        self.props = {

        }

        self.device = device

    def set_prop(self, prop, value):
        self.props[prop] = value

    def get_prop(self, prop):
        return self.props[prop]


class LaunchPad(Device):
    def __init__(self) -> None:
        super().__init__()

    def light_on_button_cc(self, cc: int, value: int):
        print(f'LaunchPad: send CC{cc} = {value} (light button on)')

    def light_off_button_cc(self, cc: int, value: int):
        print(f'LaunchPad: send CC{cc} = {value} (light button off)')

    def on_midi_noteon(self, note: int, velocity: int):
        pass

    def on_midi_noteoff(self, note: int, velocity: int):
        pass


class LaunchPadButton(Control):
    """
    Props:
    - `cc`
    - `note`
    - `lit`: bool
    """

    cc: int
    note: int
    lit: bool

    def __init__(self, device: LaunchPad) -> None:
        super().__init__(device)

    def __setattr__(self, __name: str, __value: typing.Any) -> None:
        if __name == 'lit':
            if __value:
                self.device.light_on_button_cc(self.cc, 127)
            else:
                self.device.light_off_button_cc(self.cc, 0)

        super().__setattr__(__name, __value)


class Widget:
    def __init__(self, name: str) -> None:
        self.props = {
            'visible': True
        }

        self.name = name

        self.device: typing.Optional[Device] = None

        # Iterable of '7', 'corner_button_1', 7
        self.device_pos: collections.abc.Iterable[int] = []

    def render(self):
        pass


class Container(Widget):
    def __init__(self, name: str) -> None:
        self.name = name

        # name, widget
        self.children: dict[str, Widget] = {}

    def render(self):
        for _, child in self.children.items():
            child.render()


class Button(Widget):
    on: bool = False
    # toggle: bool = False

    def __init__(self, name: str) -> None:
        super().__init__(name)

    def render(self):
        self.device.controls[self.device_pos[0]].lit = self.on

    def on_pressed(self):
        print(f'{self.name} Widget Button pressed')
        self.on = True

        self.render()

    def on_released(self):
        print(f'{self.name} Widget Button released')
        self.on = False

        self.render()


def create_button_widget(toggle: bool, color: int):
    state = False

    def _button(source):
        def on_subscribe(observer, scheduler):
            def on_next(event):
                print(f'Event to button widget: {event}')

                nonlocal state

                name, value = event

                if name == 'pressed':
                    if value == True:
                        if toggle:
                            state = True
                            observer.on_next(('lit', state))
                        else:
                            state = not state
                            observer.on_next(('lit', state))
                    else:
                        if toggle:
                            state = False
                            observer.on_next(('lit', state))

                observer.on_next(event)

            return source.subscribe(
                on_next,
                observer.on_error,
                observer.on_completed)

        return reactivex.create(on_subscribe)

    return _button


def create_launchpad_device():
    d = LaunchPad()

    #

    b = LaunchPadButton(d)
    b.cc = 12

    d.controls[7] = b

    #

    b = LaunchPadButton(d)
    b.cc = 13

    d.controls[8] = b

    return d


async def main():
    device_launchpad = create_launchpad_device()
    device_launchcontrol = Device()

    container = Container('main')

    #

    p = Container('page-tempo-buttons')

    b0 = Button('plus')
    b0.device = device_launchpad
    b0.device_pos = (7, )

    b1 = Button('minus')
    b1.device = device_launchpad
    b1.device_pos = (8, )

    p.children['plus'] = b0
    p.children['minus'] = b1

    container.children['page-tempo-buttons'] = p

    #

    p = Container('page-shuffle-buttons')

    b0 = Button('plus')
    b0.device = device_launchpad
    b0.device_pos = (7, )

    b1 = Button('minus')
    b1.device = device_launchpad
    b1.device_pos = (8, )

    p.children['plus'] = b0
    p.children['minus'] = b1
    container.children['page-shuffle-buttons'] = p

    #

    p.render()

    return

    #

    aio_scheduler = AsyncIOScheduler(loop=asyncio.get_running_loop())

    prev_button = create_prev_track_button()
    next_button = create_next_track_button()
    selected = Selected(100)

    reactivex.of(
        prev_button.pipe(create_dec_selected_track(selected)),
        next_button.pipe(create_inc_selected_track(selected))
    ).pipe(reactivex.operators.merge_all()).subscribe(
        Lcd(),
        scheduler=aio_scheduler)

    await asyncio.sleep(3)


asyncio.run(main(), debug=True)
