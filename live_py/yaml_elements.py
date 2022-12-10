import logging
from typing import Iterable, Optional, Tuple

from live_py.base import DeviceControlEvent

from . import device_control_events, yaml_namespace
from .yaml_namespace import YamlObject

logger = logging.getLogger(__name__)


class WidgetControl(YamlObject):
    """Something able to receive Device Control Events
    """

    device_name: Optional[str]
    device_control_id: Optional[int]

    def __init__(self,
                 device_name: Optional[str],
                 device_control_id: Optional[int],
                 yaml_obj: dict):
        super().__init__(yaml_obj)
        self.device_name = device_name
        self.device_control_id = device_control_id

    def __str__(self) -> str:
        return f"WidgetControl(name={self.name}, class={self.yaml_class})"

    def map_device_control_event(self, event: DeviceControlEvent) -> Optional[Tuple]:
        pass


class Button(WidgetControl):
    def __init__(self, yaml_obj: dict):
        logger.debug(f'Create from {yaml_obj}')

        super().__init__(
            device_name=yaml_obj.get('device', None),
            device_control_id=yaml_obj.get('device_control', None),
            yaml_obj=yaml_obj,
        )

    def __repr__(self) -> str:
        return f'Button("{self.name}")'

    def map_device_control_event(self, event: DeviceControlEvent) -> Optional[Tuple]:
        match event:
            case device_control_events.MidiNoteOnDeviceControlEvent():
                return ((self.name, 'value', 1))

            case device_control_events.MidiNoteOffDeviceControlEvent():
                return ((self.name, 'value', 0))

            case device_control_events.MidiNoteDeviceControlEvent():
                return ((self.name, 'value'), min(1, event.velocity))

            case _:
                return None


class Page(YamlObject):
    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj, ['active'])

        widgets_iter = (yaml_namespace.new_obj(w) for w in yaml_obj['widgets'])
        widgets_iter = filter(lambda o: o is not None, widgets_iter)

        self.widgets = list(widgets_iter)

        for w in self.widgets:
            assert(isinstance(w, WidgetControl))


class Var(YamlObject):
    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj, ['value'])


class Clock(YamlObject):
    def __init__(self, yaml_obj: dict):
        super().__init__(yaml_obj, ['tempo', 'shuffle'])


def get_widgets_in_page(page: str) -> Iterable[WidgetControl]:
    widgets = yaml_namespace.get_obj(page).widgets
    return widgets


yaml_namespace.register_class('page', Page)
yaml_namespace.register_class('button', Button)
yaml_namespace.register_class('var', Var)
yaml_namespace.register_class('clock', Clock)
