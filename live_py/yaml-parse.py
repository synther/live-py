import logging
import pprint
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

import reactivex
import yaml
from reactivex import Observable, abc
from reactivex import operators as ops
from reactivex.disposable import (CompositeDisposable,
                                  SingleAssignmentDisposable)

pp = pprint.PrettyPrinter(indent=4)

yaml_namespace = {}
yaml_classes = {}

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


def new_obj(yaml_obj: dict) -> Optional[object]:
    assert type(yaml_obj) is dict
    obj_class, obj_name = next(iter(yaml_obj.items()))

    if obj_name is None:
        obj_name = f'{obj_class}-{str(uuid.uuid4())}'

    yaml_class = yaml_classes.get(obj_class, None)

    if yaml_class:
        yaml_namespace[obj_name] = yaml_classes[obj_class](yaml_obj)
        return yaml_namespace[obj_name]
    else:
        return None


class Page:
    def __init__(self, yaml_obj: dict):
        logger.debug(f'Create Page from {yaml_obj}')

        widgets_iter = (new_obj(w) for w in yaml_obj['widgets'])
        widgets_iter = filter(lambda o: o is not None, widgets_iter)

        self.widgets = list(widgets_iter)


class Var:
    def __init__(self, yaml: dict):
        logger.debug(f'Create from {yaml}')


class Button:
    def __init__(self, yaml: dict):
        logger.debug(f'Create from {yaml}')
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
        logger.debug(f'Create from {yaml}')


T_VAR_NAME = Union[str, tuple[str, str]]


def str_to_var_name(var_name_str: str) -> T_VAR_NAME:
    if var_name_str == 'input':
        return var_name_str
    else:
        name = tuple(var_name_str.split('.'))
        return name


class Pipeline:
    def __init__(self, yaml_obj: dict, var_subjects: Dict[str, reactivex.Subject[Any]]) -> None:
        logger.debug(f'Create Pipeline from: \n{pprint.pformat(yaml_obj)}')
        self.obs = None
        self.repr = ""
        self._repr_parts = []
        self._var_subjects = var_subjects

        for pipe_element in yaml_obj['pipe']:
            self._create_pipe_element(pipe_element)

        self.repr = '[ ' + " -> ".join(self._repr_parts) + ' ]'

        assert self.obs

    def _create_pipe_element(self, pipe_element):
        match pipe_element:
            case {'map': fn, 'vars': in_vars}:
                logger.debug(f"Map: {fn}")
                logger.debug(f"Input vars: {tuple(in_vars.keys())}")
                self._repr_parts.append(fn)

                in_var_names = self._create_combine(in_vars)
                assert self.obs

                self.obs = ops.map(self._create_exec_fn(in_var_names, fn))(self.obs)

            case {'filter': fn, 'vars': in_vars}:
                logger.debug(f"Filter: {fn}")
                logger.debug(f"Input vars: {tuple(in_vars.keys())}")
                self._repr_parts.append(fn)

                in_var_names = self._create_combine(in_vars)
                assert self.obs

                self.obs = ops.filter(self._create_exec_fn(in_var_names, fn))(self.obs)

            case {'out': out_var}:
                self._repr_parts.append(out_var)
                out_var = str_to_var_name(out_var)

                logger.debug(f"Out to {out_var}")

                assert self.obs

                self.obs = self.obs.pipe(ops.do_action(
                    on_next=lambda v: self._var_subjects[out_var].on_next(v)))

            case {'one_shot': value}:
                logger.debug(f"One shot value: {value}")
                self._repr_parts.append(str(value))

                assert not self.obs

                self.obs = reactivex.of(value)

    def _parse_input_var_names(self, in_vars: Dict[str, str]) -> List[T_VAR_NAME]:
        return list(map(str_to_var_name, in_vars.keys()))

    def _create_input_var_names(self, in_vars: Dict[str, str]) -> List[T_VAR_NAME]:
        in_var_names = self._parse_input_var_names(in_vars)

        for name in in_var_names:
            if name != 'input':
                create_var(name)

        return in_var_names

    def _create_combine(self, in_vars: Dict[str, str]) -> List[T_VAR_NAME]:
        in_var_names = self._create_input_var_names(in_vars)

        def get_obs(var_name):
            obs = self.obs if var_name == 'input' else self._var_subjects[var_name]
            assert obs
            return obs

        self.obs = combine_rx(
            list(map(get_obs, in_var_names)),
            [rx_type == 'rx' for rx_type in in_vars.values()],
            in_var_names
        )

        return in_var_names

    def _create_exec_fn(self, in_var_names, in_var_fn):
        input_vars = list(in_var_names)
        var_fn = str(in_var_fn)

        def exec_fn(args):
            ns = {}

            for i, input_var in enumerate(input_vars):
                value = args[i]

                if input_var == 'input':
                    ns['input'] = value
                else:
                    obj_name, attr_name = input_var
                    obj = ns.get(obj_name, None)

                    if obj is None:
                        obj = type('', (object,), {})()
                        ns[obj_name] = obj

                    setattr(obj, attr_name, value)

            result = eval(var_fn, ns)

            logger.debug(f"Run exec. f() = {in_var_fn} = {result}")

            return result

        return exec_fn


yaml_classes['page'] = Page
yaml_classes['button'] = Button
yaml_classes['var'] = Var
yaml_classes['clock'] = Clock

var_out_subjects = {}
init_values = {}
pipelines: List[Pipeline] = []


def create_var(var_name):
    if var_out_subjects.get(var_name, None) is None:
        logger.debug(f'Create out subject for {var_name}')
        var_out_subjects[var_name] = reactivex.Subject()


def combine_rx(sources: List[Observable[Any]], is_rx: List[bool],
               from_: List[Union[str, tuple[str, str]]]) -> Observable[Tuple[Any, ...]]:
    parent = sources[0]
    assert len(sources) == len(is_rx)

    logger.debug(f'combine_rx: create combine_rx: from {from_}')

    def subscribe(
        observer: abc.ObserverBase[Any], scheduler: Optional[abc.SchedulerBase] = None
    ) -> CompositeDisposable:

        n = len(sources)
        has_value = [False] * n
        first_time_all = True
        is_done = [False] * n
        values = [None] * n

        logger.debug(f'combine_rx: subscribe to combine_rx: from {from_}')

        def _next(i: Any) -> None:
            has_value[i] = True
            nonlocal first_time_all

            logger.debug(f'combine_rx: values {values}, has_value {has_value}, from {from_}')
            logger.debug(f'combine_rx: on_next: from "{from_[i]}" = {values[i]} (is_rx={is_rx[i]})')

            if all(has_value):
                if first_time_all or is_rx[i]:
                    logger.debug(
                        f'combine_rx: pass to observer {first_time_all=}, {is_rx=}, {values=}')
                    res = tuple(values)
                    first_time_all = False
                    observer.on_next(res)

            elif all([x for j, x in enumerate(is_done) if j != i]):
                observer.on_completed()

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
                        logger.debug(f'active_pages (inserted) = {active_pages}')
                    elif not active:
                        active_pages.remove(page)
                        logger.debug(f'active_pages (removed) = {active_pages}')

            return source.subscribe(on_next,
                                    observer.on_error,
                                    observer.on_completed,
                                    scheduler=scheduler)

        return reactivex.create(subscribe)

    return _operator


def route_to_var(msg):
    var_subject = var_out_subjects.get(msg[0], None)

    if var_subject is not None:
        logger.debug(f'route {msg[1]} to {msg[0]}')
        var_subject.on_next(msg[1])


with open('set-pipelines.yaml', 'r') as stream:
    yaml_data = yaml.safe_load(stream)

    for yaml_obj in yaml_data:
        new_obj(yaml_obj)

    for yaml_obj in yaml_data:
        if 'pipeline' in yaml_obj:
            pipelines.append(Pipeline(yaml_obj, var_out_subjects))


var_out_subjects[('clock', 'tempo')].subscribe(
    on_next=lambda v: logger.info(f'clock.tempo = {v}')
)

for pipeline in pipelines:
    pipeline.obs.subscribe(
        on_next=lambda v, pipe=pipeline.repr: logger.debug(f'pipeline {pipe} on_next: {v}'),
        on_completed=lambda: logger.debug(f'pipeline on_completed'),
        on_error=lambda e: logger.debug(f'pipeline error {e}'))


reactivex.of(
    ('active', 'main', True),
    ('midicc', 'LaunchPad1', 1, 127),  # tempo dec
    ('midicc', 'LaunchPad1', 1, 0),
    ('midicc', 'LaunchPad1', 2, 127),  # tempo inc
    ('midicc', 'LaunchPad1', 2, 0),
    ('midicc', 'LaunchPad1', 3, 127),  # shift x10 pressed
    ('midicc', 'LaunchPad1', 1, 127),  # tempo dec
    ('midicc', 'LaunchPad1', 1, 0),
    ('midicc', 'LaunchPad1', 1, 127),  # tempo dec
    ('midicc', 'LaunchPad1', 1, 0),
    ('midicc', 'LaunchPad1', 2, 127),  # tempo inc
    ('midicc', 'LaunchPad1', 2, 0),
    ('midicc', 'LaunchPad1', 3, 0),  # shift x10 released
    ('midicc', 'LaunchPad1', 2, 127),  # tempo inc
    ('midicc', 'LaunchPad1', 2, 0),
    # ('active', 'shuffle', True),

    # ('midicc', 'LaunchPad1', 2, 127),
    # ('midicc', 'LaunchPad1', 2, 0),

    # ('active', 'shuffle', False),

    # ('midicc', 'LaunchPad1', 2, 127),
    # ('midicc', 'LaunchPad1', 2, 0),

    # ('midicc', 'LaunchPad2', 2, 0),
    # ('midicc', 'LaunchPad2', 2, 0),
    # ('midicc', 'LaunchPad2', 1, 0),

).pipe(
    activity_manager(
        yaml_namespace
    ),
    ops.do_action(
        on_next=lambda v: logger.debug(f'Activity Manager out: {v}'),
        on_completed=lambda: logger.debug(f'Activity Manager on_completed')
    ),
    ops.do_action(
        on_next=route_to_var
    ),
).subscribe()
