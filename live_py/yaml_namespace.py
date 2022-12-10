import dataclasses
import logging
import uuid
from typing import Iterable, Optional, Type, Dict

from . import yaml_pipelines

logger = logging.getLogger(__name__)


class YamlObject:
    def __init__(self,
                 yaml_obj: dict,
                 var_list: Iterable[str] = []):
        logger.debug(f'Create {type(self).__name__} from {yaml_obj}')

        self.yaml_class, self.name = next(iter(yaml_obj.items()))

        if self.name is None:
            self.name = f'{self.yaml_class}-{str(uuid.uuid4())}'

        self.var_subjects = {}

        for var in var_list:
            self.var_subjects[var] = yaml_pipelines.create_var((self.name, var))
            yaml_pipelines.create_pipeline({
                'pipe':
                    [
                        {'one_shot': yaml_obj[var]},
                        {'out': f'{self.name}.{var}'}
                    ]
            }, init_pipeline=True)


yaml_namespace = {}
yaml_classes: Dict[str, Type[YamlObject]] = {}


def register_class(yaml_class_name: str, klass: Type[YamlObject]):
    yaml_classes[yaml_class_name] = klass


def new_obj(yaml_obj: dict) -> Optional[YamlObject]:
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


def get_obj(name: str):
    return yaml_namespace[name]


def find_all_obj():
    yield from yaml_namespace.items()
