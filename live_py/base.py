import dataclasses
from typing import ClassVar, Dict

@dataclasses.dataclass
class DeviceControl:
    yaml_type: ClassVar[str]
    device_name: str
    control_id: int


class Device:
    controls: Dict[int, DeviceControl] = {}


@dataclasses.dataclass
class DeviceControlEvent:
    control: DeviceControl
