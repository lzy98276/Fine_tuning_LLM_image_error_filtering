from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Image, Record, Video, File as FileComponent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("image_message_filter", "YourName", "过滤图片消息的插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._wake_prefixes = ["/"]

    def _is_media_message(self, event: AstrMessageEvent) -> bool:
        chain = event.get_messages()
        return any(isinstance(seg, (Image, Record, Video, FileComponent)) for seg in chain)

    def _normalize_wake_prefixes(self, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, (list, tuple, set)):
            prefixes = []
            for item in value:
                if isinstance(item, str) and item:
                    prefixes.append(item)
            return prefixes
        return []

    def _extract_wake_prefixes_from_mapping(self, mapping):
        if not isinstance(mapping, dict):
            return []
        prefixes = []
        prefixes.extend(self._normalize_wake_prefixes(mapping.get("wake_prefix")))
        provider_settings = mapping.get("provider_settings")
        if isinstance(provider_settings, dict):
            prefixes.extend(self._normalize_wake_prefixes(provider_settings.get("wake_prefix")))
        return prefixes

    def _load_wake_prefixes_from_context(self):
        ctx = getattr(self, "context", None)
        if ctx is None:
            return []

        candidates = []
        for attr in ("config", "cfg", "settings", "bot_config", "config_dict"):
            try:
                val = getattr(ctx, attr)
            except Exception:
                continue
            if isinstance(val, dict):
                candidates.append(val)

        for method_name in ("get_config", "get_config_dict", "get_cmd_config", "get_settings"):
            fn = getattr(ctx, method_name, None)
            if not callable(fn):
                continue
            try:
                val = fn()
            except Exception:
                continue
            if isinstance(val, dict):
                candidates.append(val)

        prefixes = []
        for mapping in candidates:
            prefixes.extend(self._extract_wake_prefixes_from_mapping(mapping))
        return prefixes

    def _has_wake_prefix(self, event: AstrMessageEvent) -> bool:
        text = getattr(event, "message_str", "") or ""
        text = text.lstrip()
        for prefix in self._wake_prefixes:
            if prefix and text.startswith(prefix):
                return True
        return False

    def _log_block(self, event: AstrMessageEvent, stage: str, reason: str):
        msg = getattr(event, "message_obj", None)
        logger.info(
            "已屏蔽消息（无回复，停止传播）。阶段=%s 原因=%s 文档=%s 消息ID=%s 会话ID=%s 群组ID=%s 消息链=%s",
            stage,
            reason,
            "https://docs.astrbot.app/dev/star/guides/listen-message-event.html",
            getattr(msg, "message_id", None),
            getattr(msg, "session_id", None),
            getattr(msg, "group_id", None),
            event.get_messages(),
        )

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        prefixes = self._load_wake_prefixes_from_context()
        if prefixes:
            self._wake_prefixes = prefixes

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if self._is_media_message(event):
            self._log_block(event, "on_message", "media_message")
            event.stop_event()

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req):
        if self._is_media_message(event):
            self._log_block(event, "on_llm_request", "media_message")
            event.stop_event()
            return

        if not self._has_wake_prefix(event):
            self._log_block(event, "on_llm_request", "missing_wake_prefix")
            event.stop_event()

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        if not self._is_media_message(event) and self._has_wake_prefix(event):
            return
        result = event.get_result()
        if result is not None and hasattr(result, "chain"):
            chain = getattr(result, "chain", None)
            if hasattr(chain, "clear"):
                chain.clear()
            else:
                setattr(result, "chain", [])
        reason = "media_message" if self._is_media_message(event) else "missing_wake_prefix"
        self._log_block(event, "on_decorating_result", reason)
        event.stop_event()

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
