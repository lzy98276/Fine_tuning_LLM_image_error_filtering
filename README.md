# astrbot_plugin_image_message_filtering

用于在 AstrBot 消息管道中“拦截非文本/媒体类消息”，避免后续插件或 LLM 处理图片等内容导致报错，同时保留正常聊天触发逻辑（唤醒词/@/回复/戳一戳）。

## 功能

### 1) 直接拦截（不回复、不发送）

当收到以下消息类型时，会在消息管道早期直接 `stop_event()`，只记录日志，不让后续流程（含 LLM 调用、发送回复）继续：

- 图片：Image
- 语音：Record
- 视频：Video
- 文件：File
- 引用/回复中包含上述媒体类型（仅按明确的类型判断，不会因为链接文本误拦截）

### 2) 控制 LLM 触发条件

对“非媒体消息”，仅在满足任一条件时允许进入 LLM：

- 以配置的唤醒词开头（wake_prefix）
- 群聊中 @ 机器人
- 回复/引用（reply/quote/source 等，取决于平台 raw_message）
- 戳一戳（Poke）
- 私聊且配置 `friend_message_needs_wake_prefix=false`（则不需要唤醒词）

其余消息会在 `on_llm_request` 阶段被阻止传播，不回复、不调用模型。

## 配置说明

插件会尽可能从运行时配置里读取唤醒词：

- `wake_prefix`（例如：`["/"]`）
- 或 `provider_settings.wake_prefix`

未读取到时默认使用 `/`。

## 日志

每次拦截都会输出一条日志，包含：

- 阶段（on_message / on_llm_request / on_decorating_result）
- 原因（media_message / quoted_media_message / no_wake_prefix_or_mention_or_reply）
- message_id / session_id / group_id
- 消息链摘要

## 代码入口

- 插件入口：[main.py](file:///d:/GitHub/Fine_tuning_LLM_image_error_filtering/main.py)
- 插件元信息：[metadata.yaml](file:///d:/GitHub/Fine_tuning_LLM_image_error_filtering/metadata.yaml)

## 相关文档

- 处理消息事件：https://docs.astrbot.app/dev/star/guides/listen-message-event.html
- 插件开发文档：https://docs.astrbot.app/dev/star/plugin-new.html
