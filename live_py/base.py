import dataclasses
from typing import ClassVar, List, Optional

from . import yaml_namespace
from .yaml_namespace import YamlObject


class Device(YamlObject):
    controls: List["DeviceControl"] = []

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj, [])

        for yaml_control in yaml_obj['controls']:
            control = yaml_namespace.new_obj(yaml_control)

            if control:
                assert isinstance(control, DeviceControl)
                control.device = self
                self.controls.append(control)


class DeviceControl(YamlObject):
    yaml_type: ClassVar[str]
    device: Device
    control_id: Optional[int]

    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj,
                         var_list=[
                             'events_in',
                             'events_out',
                         ])
        self.control_id = yaml_obj.get('id', None)

    def send(self, msg: "DeviceControlEvent"):
        pass


@dataclasses.dataclass
class DeviceControlEvent:
    control: Optional[DeviceControl]
    """`control` which produced the event. None if the event was created during processing
    """
