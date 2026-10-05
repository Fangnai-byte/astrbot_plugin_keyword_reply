# astrbot_plugin_keyword_reply ｜ 关键词自动回复

<img src="logo.png" width="140" alt="logo">

监测到「内容」就发送「内容」，可附带一张图片，并带冷却时间防止刷屏。

## 特性

- **规则自定义**：想监测什么、回什么，全在配置里写，无需改代码
- **附带图片**：只写图名即可（自动在图片目录里找并补扩展名），也支持绝对路径和 http(s) 链接
- **防刷屏**：同一条规则在冷却时间内不重复发送，冷却范围可选按群 / 按人 / 全局
- **不重复回复**：同一条触发词刚刚在「上面」出现过就跳过，可在配置里用一个开关随时关掉
- **三种匹配**：`contains`（包含，默认）/ `exact`（完全相等）/ `regex`（正则）
- **开关齐全**：群聊、私聊分别开关；机器人自己发的消息默认不触发（防死循环）；可设用户黑名单
- **改配置即生效**：在 WebUI 里改规则后不需要重载插件

## 规则写法

每条一行，逗号分隔：

```
触发词，回复内容，图片，冷却秒数
```

后三项都可以省略：

| 配置 | 含义 |
|---|---|
| `姆唔，姆唔，tu_1` | 监测到「姆唔」→ 回复「姆唔」+ 图片 `tu_1` |
| `早安，早安哦` | 只回复文字 |
| `晚安，，tu_2，120` | 只发图，冷却 120 秒 |
| `你是笨蛋，哼，别说了` | 回复「哼，别说了」（注意：回复里带逗号时请用 JSON 写法） |

图片只写图名时，会在 `image_dir`（默认 `/root/AstrBot/data/workspaces/tu`）里查找，
`tu_1` 会自动匹配 `tu_1.png` / `tu_1.jpg` 等。

### 高级写法（JSON）

规则列表也支持 JSON 数组，字段更灵活，回复内容里可以带逗号：

```json
[
  {"keyword": "姆唔", "reply": "姆唔，姆唔", "image": "tu_1"},
  {"keyword": "早安", "reply": "早安哦", "cooldown": 60},
  {"keyword": "^好耶+$", "reply": "好耶！", "match_type": "regex", "image": "https://example.com/a.png"}
]
```

字段：`keyword`（必填）、`reply`、`image`、`match_type`、`cooldown`。

## 配置项

| 配置 | 默认 | 说明 |
|---|---|---|
| `rules` | `[]` | 规则列表，见上 |
| `match_type` | `contains` | 默认匹配方式 |
| `cooldown_seconds` | `30` | 默认冷却秒数，0 为不限制 |
| `cooldown_scope` | `group` | 冷却范围：`group` / `user` / `global` |
| `cooldown_hint` | 空 | 冷却期间只提示一次的话术，留空则静默 |
| `image_dir` | `/root/AstrBot/data/workspaces/tu` | 图片名查找目录 |
| `enable_group` | `true` | 群里是否生效 |
| `enable_private` | `true` | 私聊是否生效 |
| `ignore_bot` | `true` | 忽略机器人自己的消息 |
| `ignore_user_ids` | `[]` | 不触发回复的 QQ 号 |
| `ignore_group_ids` | `[]` | 不触发回复的 QQ 群号 |
| `no_quote` | `true` | 回复时不引用原消息（直接发送，绕过框架的引用装饰） |
| `dedup_enabled` | `true` | 上面已有触发词就不再回复（去重总开关，配置界面里就是一个开关） |
| `dedup_window` | `1` | 往上检查几条消息，`1` 只看紧邻的上一条 |
| `dedup_seconds` | `0` | 只统计这么多秒以内的上面消息，`0` 表示不限时间 |
| `dedup_same_user_only` | `false` | 只算同一个人说的；默认关闭，即上面谁说过都算 |

## 行为说明

- 一条消息只触发**第一条**命中的规则，按配置顺序优先。
- 命中后会先看去重：**上面已经出现过这条触发词就不再回复**（`dedup_enabled` 关闭则跳过这一步）。
  例如 A 先发「唔姆」，紧接着又发一次「唔姆」，第二次就不发了。
- 去重只看「上面」的消息，不看本条自己；记录按会话（群 / 私聊）隔离，只存内存，重启即清空。
- 命中后先判断冷却，冷却中不发送（配置了 `cooldown_hint` 则最多提示一次）。
- 规则只有图片但图片找不到时，不会发送空消息，会在日志里给出警告。
- 冷却记录保存在内存里，插件重载或 AstrBot 重启后清空。

## 目录结构

```
main.py           插件主体：消息监听、命中判定、发送
reply_core.py     纯逻辑：规则解析、匹配、冷却、图片解析（可离线测试）
_conf_schema.json WebUI 配置 schema
metadata.yaml     插件元信息
tests/test_reply_core.py 离线单元测试
```

## 测试

```bash
python3 tests/test_reply_core.py
```
