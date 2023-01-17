import logging
import uuid
import reactivex
from typing import Dict, Iterable, List, Optional, Type, TypeVar

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

        self.var_subjects: Dict[str, reactivex.Subject] = {}

        for var in var_list:
            self.var_subjects[var] = yaml_pipelines.create_var((self.name, var))

            if var in yaml_obj:
                yaml_pipelines.create_pipeline({
                    'pipe':
                        [
                            {'one_shot': yaml_obj[var]},
                            {'out': f'{self.name}.{var}'}
                        ]
                }, init_pipeline=True)


yaml_namespace: Dict[str, YamlObject] = {}
yaml_classes: Dict[str, Type[YamlObject]] = {}


def register_class(yaml_class_name: str, klass: Type[YamlObject]):
    yaml_classes[yaml_class_name] = klass


def new_obj(yaml_obj: dict) -> Optional[YamlObject]:
    assert type(yaml_obj) is dict

    obj_class, _ = next(iter(yaml_obj.items()))
    yaml_class = yaml_classes.get(obj_class, None)

    if yaml_class:
        obj = yaml_class(yaml_obj)
        yaml_namespace[obj.name] = obj
        return obj
    else:
        return None


def get_obj(name: str):
    return yaml_namespace[name]


def find_all_obj():
    yield from yaml_namespace.items()


T = TypeVar('T')


def find_by_class(klass: Type[T]) -> List[T]:
    # TODO fix O(n)

    return [
        obj for obj in yaml_namespace.values() if isinstance(obj, klass)
    ]
