from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Image, Record, Video, File as FileComponent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("image_message_filter", "YourName", "过滤图片消息的插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        chain = event.get_messages()
        if any(isinstance(seg, (Image, Record, Video, FileComponent)) for seg in chain):
            logger.info("过滤图片/语音/视频/文件消息: %s", chain)
            yield event.plain_result("检测到图片/语音/视频/文件消息，已过滤。")
            event.stop_event()

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
