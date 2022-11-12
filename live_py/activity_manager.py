import logging
from typing import Optional

import reactivex

from . import yaml_elements
from .base import DeviceControl, DeviceControlEvent

logger = logging.getLogger(__name__)


def activity_manager():
    active_pages = []

    # TODO make activity manager applicable to either midi cc or color message
    # like a filter for only visible widgets

    def on_page_active_changed(page: str, active: bool):
        if active:
            if page in active_pages:
                active_pages.remove(page)

            active_pages.insert(0, page)
            logger.debug(f'active_pages (inserted) = {active_pages}')
        elif not active:
            try:
                active_pages.remove(page)
            except ValueError:
                pass

            logger.debug(f'active_pages (removed) = {active_pages}')

    def find_top_widget(device_control: DeviceControl) -> Optional[yaml_elements.WidgetControl]:
        for active_page in active_pages:
            for widget in yaml_elements.get_widgets_in_page(active_page):
                if (widget.device_name, widget.device_control_id) == (
                        device_control.device_name,
                        device_control.control_id):
                    return widget

        return None

    def _operator(source):
        def subscribe(observer, scheduler=None):
            def on_next(value):
                logger.debug(f"Activity manager: on_next {value}")

                match value:
                    case DeviceControlEvent():
                        affected_widget = find_top_widget(value.control)

                        if affected_widget:
                            logger.debug(f"Pass {value} + {affected_widget}")
                            observer.on_next((value, affected_widget))
                        else:
                            logger.debug(f"Reject {value}")

                    case ((obj, var), value):
                        logger.debug(f"Variable arrived, {obj}.{var} = {value}")

                        if var == 'active':
                            on_page_active_changed(obj, value)

            return source.subscribe(on_next,
                                    observer.on_error,
                                    observer.on_completed,
                                    scheduler=scheduler)

        return reactivex.create(subscribe)

    return _operator
