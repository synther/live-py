import abc
import dataclasses
from typing import Any, ClassVar, Dict


@dataclasses.dataclass
class DeviceControl:
    yaml_type: ClassVar[str]
    device_name: str
    control_id: int

    @classmethod
    @abc.abstractmethod
    def create_from_yaml(cls, device_name: str, control_id: int, control_props: Dict[str, Any]):
        ...


class Device:
    controls: Dict[int, DeviceControl] = {}


@dataclasses.dataclass
class DeviceControlEvent:
    control: DeviceControl
