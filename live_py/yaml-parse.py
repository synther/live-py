import pprint
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import reactivex
import yaml
from reactivex import Observable, abc
from reactivex import operators as ops
from reactivex.disposable import (CompositeDisposable,
                                  SingleAssignmentDisposable)

pp = pprint.PrettyPrinter(indent=4)

yaml_namespace = {}
yaml_classes = {}


def new_obj(yaml_obj: dict):
    assert type(yaml_obj) is dict
    obj_class, obj_name = next(iter(yaml_obj.items()))
    yaml_namespace[obj_name] = yaml_classes[obj_class](yaml_obj)
    return yaml_namespace[obj_name]


class Page:
    def __init__(self, yaml_obj: dict):
        print(f'Create Page from {yaml_obj}')

        self.widgets = [new_obj(w) for w in yaml_obj['widgets']]


class Var:
    def __init__(self, yaml: dict):
        print(f'Create from {yaml}')


class Filter:
    def __init__(self, yaml: dict):
        print(f'Create from {yaml}')


class Button:
    def __init__(self, yaml: dict):
        print(f'Create from {yaml}')
        self.name = next(iter(yaml.items()))[1]
        self.hw = yaml.get('hw', None)
        self.hw_pos = yaml.get('hw_pos', None)

    def __repr__(self) -> str:
        return f'Button("{self.name}")'

    def process_hw_message(self, msg: Tuple) -> Tuple:
        """
        Process midi event: (<name>, <value>)
        """

        return ((msg[0], 'value'), min(1, msg[1]))


class Clock:
    def __init__(self, yaml: dict):
        print(f'Create from {yaml}')


yaml_classes['page'] = Page
yaml_classes['button'] = Button
yaml_classes['var'] = Var
yaml_classes['clock'] = Clock
yaml_classes['filter'] = Filter

var_in_subjects = {}
var_out_subjects = {}
var_obs = {}


def create_var(var_name):
    if var_in_subjects.get(var_name, None) is None:
        print(f'Create in subject for {var_name}')
        var_in_subjects[var_name] = reactivex.Subject()

    if var_out_subjects.get(var_name, None) is None:
        print(f'Create out subject for {var_name}')
        var_out_subjects[var_name] = reactivex.Subject()

    if var_obs.get(var_name, None) is None:
        print(f'Create ops list for {var_name}')
        var_obs[var_name] = []


@dataclass
class BindInputVar:
    name: tuple[str, str]
    rx: bool


def combine_rx(sources: List[Observable[Any]], is_rx: List[bool],
               from_: List[str]) -> Observable[Tuple[Any, ...]]:
    parent = sources[0]
    assert len(sources) == len(is_rx)

    print(f'combine_rx: create combine_rx: from {from_}')

    def subscribe(
        observer: abc.ObserverBase[Any], scheduler: Optional[abc.SchedulerBase] = None
    ) -> CompositeDisposable:

        n = len(sources)
        has_value = [False] * n
        has_value_all = False
        is_done = [False] * n
        values = [None] * n

        print(f'combine_rx: subscribe to combine_rx: from {from_}')

        def _next(i: Any) -> None:
            has_value[i] = True
            nonlocal has_value_all

            print(f'combine_rx: values {values}, has_value {has_value}')
            print(f'combine_rx: on_next on combine_rx: from {from_}')

            if has_value_all or all(has_value):
                first_time_all = not has_value_all

                if first_time_all or is_rx[i]:
                    res = tuple(values)
                    print(f'combine_rx: pass to observer')
                    observer.on_next(res)

            elif all([x for j, x in enumerate(is_done) if j != i]):
                observer.on_completed()

            has_value_all = all(has_value)

        def done(i: Any) -> None:
            is_done[i] = True
            if all(is_done):
                observer.on_completed()

        subscriptions: List[Optional[SingleAssignmentDisposable]] = [None] * n

        def func(i: int) -> None:
            subscriptions[i] = SingleAssignmentDisposable()

            def on_next(x: Any) -> None:
                with parent.lock:
                    values[i] = x
                    _next(i)

            def on_completed() -> None:
                with parent.lock:
                    done(i)

            subscription = subscriptions[i]
            assert subscription
            subscription.disposable = sources[i].subscribe(
                on_next, observer.on_error, on_completed, scheduler=scheduler
            )

        for idx in range(n):
            func(idx)
        return CompositeDisposable(subscriptions)

    return Observable(subscribe)


def create_binds(objs):
    for yaml_obj in objs:
        bind_list = yaml_obj.get('bind', None)

        if bind_list:
            print(f'Create binds for {yaml_obj}')

            for bind_obj in bind_list:
                var_name, var_fn = next(iter(bind_obj.items()))
                var_name = tuple(var_name.split('.'))

                print(f'Bind: {var_name} <- {var_fn}')

                # combine_subjects = []
                input_vars: list[BindInputVar] = []

                create_var(var_name)

                for input_var_obj in bind_obj['input']:
                    input_var, input_var_rx = next(iter(input_var_obj.items()))
                    input_var = tuple(input_var.split('.'))
                    input_var_rx = input_var_rx == 'rx'
                    print(f'  Input var: {input_var} rx = {input_var_rx}')

                    create_var(input_var)
                    input_vars.append(BindInputVar(input_var, input_var_rx))
                    # combine_subjects.append(var_out_subjects[input_var])

                def create_exec_fn(in_input_vars, in_var_fn):
                    input_vars = list(in_input_vars)
                    var_fn = str(in_var_fn)

                    def exec_fn(args):
                        ns = {}

                        for i, input_var in enumerate(input_vars):
                            obj_name, attr_name = input_var.name
                            obj = ns.get(obj_name, None)

                            if obj is None:
                                obj = type('', (object,), {})()
                                ns[obj_name] = obj

                            setattr(obj, attr_name, args[i])

                        return eval(var_fn, ns)

                    return exec_fn

                var_obs[var_name].append(
                    combine_rx(
                        [var_out_subjects[v.name] for v in input_vars],
                        [v.rx for v in input_vars],
                        [v.name for v in input_vars]
                    ).pipe(
                        ops.map(create_exec_fn(input_vars, var_fn))
                    )
                )

        if 'widgets' in yaml_obj:
            create_binds(yaml_obj['widgets'])


with open('set.yaml', 'r') as stream:
    yaml_data = yaml.safe_load(stream)

    for obj in yaml_data:
        new_obj(obj)

    create_binds(yaml_data)

    # pp.pprint(yaml_data)


# print(yaml_namespace)


def activity_manager(yaml_namespace):
    active_pages = []

    # TODO make activity manager applicable to either midi cc or color message
    # like a filter for only visible widgets

    def _operator(source):
        def subscribe(observer, scheduler=None):
            def on_next(value):
                if value[0] == 'midicc':
                    _, hw, hw_pos, cc = value
                    for active_page in active_pages:
                        for w in yaml_namespace[active_page].widgets:
                            if (hw, hw_pos) == (w.hw, w.hw_pos):
                                observer.on_next(w.process_hw_message((w.name, cc)))
                                return

                if value[0] == 'active':
                    _, page, active = value

                    if active:
                        active_pages.insert(0, page)
                        print(f'active_pages (inserted) = {active_pages}')
                    elif not active:
                        active_pages.remove(page)
                        print(f'active_pages (removed) = {active_pages}')

            return source.subscribe(on_next,
                                    observer.on_error,
                                    observer.on_completed,
                                    scheduler=scheduler)

        return reactivex.create(subscribe)

    return _operator


var_out_subjects[('clock', 'tempo')].subscribe(
    on_next=lambda v: print(f'clock.tempo {v}'),
    on_error=lambda v: print(f'clock.tempo error {v}'),
    on_completed=lambda: print(f'clock.tempo on_completed')
)

for var_name in var_out_subjects.keys():
    if not var_obs[var_name]:
        var_in_subjects[var_name].subscribe(var_out_subjects[var_name])
    else:
        for ob in var_obs[var_name]:
            print(f'Subscribe {var_name} out subject to its obs')
            ob.subscribe(var_out_subjects[var_name])

# var_in_subjects[('inc_static', 'value')].on_next(2)
# var_in_subjects[('shift_inc', 'value')].on_next(1)

# var_in_subjects[('shift_inc', 'value')].on_next(3)
# var_in_subjects[('inc_static', 'value')].on_next(4)
# var_in_subjects[('shift_inc', 'value')].on_next(5)
# var_in_subjects[('inc_static', 'value')].on_next(4)
# var_in_subjects[('shift_inc', 'value')].on_next(3)

# var_in_subjects[('shift_inc', 'value')].on_next(9)
# var_in_subjects[('shift_inc', 'value')].on_next(9)
# var_in_subjects[('shift_inc', 'value')].on_next(9)
# var_in_subjects[('inc_static', 'value')].on_next(0)
# var_in_subjects[('inc_static', 'value')].on_next(0)
# var_in_subjects[('shift_inc', 'value')].on_next(10)
# var_in_subjects[('inc_static', 'value')].on_next(1000)
# var_in_subjects[('inc_static', 'value')].on_next(1001)

def route_to_var(msg):
    var_subject = var_in_subjects.get(msg[0], None)

    if var_subject is not None:
        print(f'route {msg[1]} to {msg[0]}')
        var_subject.on_next(msg[1])

reactivex.of(
    ('active', 'main', True),
    ('midicc', 'LaunchPad1', 1, 127),
    ('midicc', 'LaunchPad1', 1, 0),
    ('midicc', 'LaunchPad1', 2, 127),
    ('midicc', 'LaunchPad1', 2, 0),
    ('midicc', 'LaunchPad1', 3, 127),
    ('midicc', 'LaunchPad1', 3, 0),
    ('midicc', 'LaunchPad1', 1, 127),
    ('midicc', 'LaunchPad1', 1, 0),


    ('active', 'shuffle', True),

    ('midicc', 'LaunchPad1', 2, 127),
    ('midicc', 'LaunchPad1', 2, 0),

    ('active', 'shuffle', False),

    ('midicc', 'LaunchPad1', 2, 127),
    ('midicc', 'LaunchPad1', 2, 0),

    ('midicc', 'LaunchPad2', 2, 0),
    ('midicc', 'LaunchPad2', 2, 0),
    ('midicc', 'LaunchPad2', 1, 0),
).pipe(activity_manager(yaml_namespace),
       ops.do_action(on_next=route_to_var)).subscribe(
    on_next=lambda v: print(f'Activity Manager on_next: {v}'),
    on_completed=lambda: print(f'Activity Manager on_completed')
)

# reactivex.case
