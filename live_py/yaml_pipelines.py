import logging
import pprint
from typing import Any, Dict, List, Optional, Union

import reactivex
from reactivex import operators as ops

from .combine_rx import combine_rx

logger = logging.getLogger(__name__)

# TODO a pipeline stops on the first error?


def create_var(var_name):
    subj = var_out_subjects.get(var_name, None)
    if subj is None:
        logger.debug(f'Create out subject for {var_name}')
        subj = reactivex.Subject()
        var_out_subjects[var_name] = subj

    return subj


def get_var_subject(var_name: tuple[str, str]) -> Optional[reactivex.Subject]:
    return var_out_subjects.get(var_name, None)


def create_pipeline(yaml_obj, init_pipeline=False, silent=False):
    pipeline = Pipeline(yaml_obj, var_out_subjects, silent)

    if init_pipeline:
        pipelines.append(pipeline)
    else:
        pipelines.insert(0, Pipeline(yaml_obj, var_out_subjects, silent))


T_VAR_NAME = Union[str, tuple[str, str]]


def str_to_var_name(var_name_str: str) -> T_VAR_NAME:
    if var_name_str == 'input':
        return var_name_str
    else:
        name = tuple(var_name_str.split('.'))
        return name


class Pipeline:
    def __init__(self,
                 yaml_obj: dict,
                 var_subjects: Dict[tuple[str, str], reactivex.Subject[Any]],
                 silent: bool = False,
                 ) -> None:
        logger.debug(f'Create Pipeline from: \n{pprint.pformat(yaml_obj)}')
        self.obs = None
        self.repr = ""
        self._repr_parts = []
        self._var_subjects = var_subjects
        self._silent = silent

        if 'silent' in yaml_obj:
            self._silent = yaml_obj['silent']

        for pipe_element in yaml_obj['pipe']:
            self._create_pipe_element(pipe_element)

        self.repr = '[ ' + " -> ".join(self._repr_parts) + ' ]'

        assert self.obs

    def _create_pipe_element(self, pipe_element):
        # TODO add "input" var implicitly. is it rx or static?

        match pipe_element:
            case {'map': fn, 'vars': in_vars}:
                logger.debug(f"Map: {fn}")
                logger.debug(f"Input vars: {tuple(in_vars.keys())}")
                self._repr_parts.append(str(fn))

                in_var_names = self._create_combine(in_vars)
                assert self.obs

                self.obs = ops.map(self._create_exec_fn(in_var_names, fn))(self.obs)

            case {'filter': fn, 'vars': in_vars}:
                logger.debug(f"Filter: {fn}")
                logger.debug(f"Input vars: {tuple(in_vars.keys())}")
                self._repr_parts.append(str(fn))

                in_var_names = self._create_combine(in_vars)
                assert self.obs

                self.obs = ops.filter(self._create_exec_fn(in_var_names, fn))(self.obs)

            case {'out': out_var}:
                self._repr_parts.append(str(out_var))
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
            in_var_names,
            silent=self._silent,
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

            if not self._silent:
                logger.debug(f"Run exec. f() = {in_var_fn} = {result}")

            return result

        return exec_fn


var_out_subjects: Dict[tuple[str, str], reactivex.Subject] = {}
pipelines: List[Pipeline] = []
