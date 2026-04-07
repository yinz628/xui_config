# X-UI Port Pool Generator Minimal Spec

- 日期：2026-04-07
- 状态：Draft
- 范围：本 spec 仅确定 `mapping.yaml` 结构、节点稳定键、端口分配策略、输出边界

## 1. 背景与目标

当前仓库已有一版从单个 Clash 风格 YAML 直接生成 Xray 配置的脚本，但它仍依赖固定输入文件和预先展开的 `listeners/proxies` 结构。目标架构已经升级为一条稳定的流水线：

`subscription sources -> rule groups -> stable port pool -> xray config`

该流水线的核心目标不是“转换一个 YAML 文件”，而是“通过一份简单配置，把多源订阅节点稳定映射到固定端口段，供下游软件长期复用”。

本 spec 的直接目标：

1. 去掉“固定源文件名”假设，随机文件名只允许作为缓存产物。
2. 明确配置入口、稳定键、端口分配和输出边界，作为后续实现的硬约束。

本 spec 的非目标：

1. 不定义完整健康检查策略。
2. 不定义直接写入 `x-ui.db` 的实现细节。
3. 不定义调度、cron、systemd、服务重载细节。

## 2. 决策一：`mapping.yaml` 结构

`mapping.yaml` 是唯一受支持的人工维护入口。订阅下载后的本地文件名不是配置契约，不允许参与业务逻辑判断。

### 2.1 顶层结构

```yaml
version: 1

sources:
  - id: airport_a
    url: https://example.com/sub-a
    enabled: true
    format: clash

  - id: airport_b
    url: https://example.com/sub-b
    enabled: true
    format: clash

groups:
  - name: tg_hk
    filter: '(?i)(hk|hong kong|香港)'
    exclude: '(?i)(iepl|iplc)'
    port_range:
      start: 20000
      end: 20049
    source_ids: [airport_a, airport_b]

  - name: browser_us
    filter: '(?i)(us|united states|美国)'
    port_range:
      start: 21000
      end: 21099

runtime:
  cache_dir: ./cache/subscriptions
  state_path: ./state/port_bindings.json
  output_path: ./config.generated.json
  report_path: ./config.generated.report.json
  output_mode: config_json
```

### 2.2 字段约束

- `version`：配置版本号，首版固定为 `1`
- `sources[].id`：稳定且唯一的人类可读标识；后续状态绑定依赖它，修改后视为新源
- `sources[].url`：订阅地址
- `sources[].enabled`：是否启用；缺省视为 `true`
- `sources[].format`：首版仅支持 `clash`
- `groups[].name`：逻辑组唯一标识
- `groups[].filter`：正则表达式，基于规范化后的节点显示名做匹配
- `groups[].exclude`：可选排除规则
- `groups[].port_range`：闭区间，且不同组之间不得重叠
- `groups[].source_ids`：可选；缺省表示接收所有启用源
- `runtime.cache_dir`：订阅缓存目录
- `runtime.state_path`：稳定端口映射状态文件
- `runtime.output_mode`：首版固定为 `config_json`

### 2.3 输入与缓存规则

- 订阅抓取后可以保存为任意文件名，例如 `RH5SFz15rrci.yaml`
- 该随机文件名只允许作为抓取缓存名，不允许进入规则匹配、稳定映射或输出标签逻辑
- 实现层应将缓存统一落到 `cache_dir/<source_id>.yaml` 或 `cache_dir/<url_hash>.yaml`，但这属于内部实现，不属于用户配置契约

## 3. 决策二：节点稳定键

为兼顾“连接身份稳定”和“同名节点尽量保持同端口”，节点绑定采用双层键模型。

### 3.1 主稳定键：`node_uid`

`node_uid` 是端口绑定的主键，基于节点的规范化连接信息生成，不基于原始文件名。

规范化输入至少包含：

- `source_id`
- `protocol`
- `server`
- `server_port`
- 协议认证核心字段摘要
- 传输层关键参数摘要
- TLS 关键参数摘要

生成规则：

1. 先将节点解析为统一内部模型
2. 提取真正影响连通性的核心字段
3. 对字段按固定顺序序列化
4. 使用 `sha256` 计算摘要，取前 24 个十六进制字符作为 `node_uid`

说明：

- `source_id` 纳入主键，避免多源出现完全同名、同地址但语义不同的混淆
- 节点显示名不作为主键字段，避免 emoji、编码差异、命名风格变化导致主键漂移

### 3.2 亲和键：`name_affinity_key`

为尽量满足“同一节点名 = 同一端口”的使用体验，再引入辅助键 `name_affinity_key`。

`name_affinity_key` 基于规范化后的显示名生成，规范化规则：

1. Unicode NFKC
2. 转小写
3. 去掉多余空白
4. 可选去掉国家旗帜 emoji 与装饰性符号

### 3.3 使用规则

- 端口持久绑定优先依赖 `node_uid`
- 当某个旧节点的 `node_uid` 消失，但同组内出现相同 `name_affinity_key` 的新节点时，可以尝试复用原端口
- `name_affinity_key` 只是复用提示，不可覆盖已被其他活跃 `node_uid` 占用的端口

结论：

- “同一节点”由 `node_uid` 保证强一致
- “同一名字尽量同端口”由 `name_affinity_key` 提供弱亲和

## 4. 决策三：端口分配策略

端口分配以“组内稳定、最小扰动、绝不跨组抢占”为原则。

### 4.1 分组命中规则

- 每个节点最多进入一个组
- 组匹配顺序按 `mapping.yaml` 中 `groups` 的声明顺序执行
- 采用 `first match wins`
- 命中 `filter` 且不命中 `exclude` 时进入该组
- 未命中任何组的节点直接丢弃，并写入报告

### 4.2 组内端口规则

- 每个组拥有独立端口闭区间 `[start, end]`
- 端口只在当前组内分配，不允许借用其他组的空闲端口
- 端口分配顺序为从小到大

### 4.3 绑定与复用规则

每次生成时按以下优先级分配：

1. 若 `node_uid` 已存在历史绑定，则复用原端口
2. 否则，若存在同组且空闲的 `name_affinity_key` 历史端口，则复用该端口
3. 否则，分配本组当前最小空闲端口
4. 若组内无空闲端口，则该节点不进入输出，并记录 `group_capacity_exceeded`

### 4.4 状态文件最小结构

`runtime.state_path` 至少记录：

```json
{
  "version": 1,
  "groups": {
    "tg_hk": {
      "20000": {
        "node_uid": "a1b2c3d4e5f6",
        "name_affinity_key": "hk-01",
        "source_id": "airport_a",
        "last_seen_at": "2026-04-07T09:00:00Z",
        "status": "active"
      }
    }
  }
}
```

### 4.5 不允许的行为

- 不允许因新增节点而整体重排某个组的历史端口
- 不允许把一个节点同时映射到多个端口，除非未来明确引入副本策略
- 不允许在组满时自动溢出到其他组

## 5. 决策四：输出边界

首版实现只做“编译器”，不做“控制面”。

### 5.1 必须输出

每次执行必须产出三类文件：

1. `config.generated.json`
2. `config.generated.report.json`
3. `state/port_bindings.json`

### 5.2 输出职责

`config.generated.json` 负责：

- 为每个已分配节点生成一个 inbound
- 为每个已分配节点生成一个 outbound
- 生成 1:1 的 routing 规则
- 保留模板中的 `api/direct/blocked/warp` 等系统级 outbound

`config.generated.report.json` 负责：

- 记录源数量、节点数量、组命中数量、成功分配数量
- 记录未命中组、组容量不足、节点解析失败、协议不支持等问题
- 记录本次是否发生端口复用、端口新增、端口释放

`state/port_bindings.json` 负责：

- 持久化组内端口绑定关系
- 为下次运行提供稳定映射依据

### 5.3 首版明确不做

- 不直接写入 `x-ui.db`
- 不直接调用 x-ui 内部 API
- 不承担服务重载职责

如果需要与 X-UI 联动，首版推荐方式是：

1. 先生成 `config.generated.json`
2. 再由外部脚本完成替换、校验、重载

这样可以保持配置编译逻辑和运行控制逻辑解耦。

## 6. 最小验收标准

当后续实现完成时，至少满足：

1. 用户只改 `mapping.yaml` 即可新增订阅源和逻辑组
2. 原始订阅即使保存成随机文件名，也不影响分组和端口稳定性
3. 同一 `node_uid` 在多次运行后保持同一端口
4. 同名节点在主键变化但端口可复用时，尽量保留原端口
5. 组满、未命中、解析失败都会进入报告，而不是静默丢失

## 7. 下一步

该 spec 通过后，下一步只需要继续细化一份实现计划，拆成：

1. 订阅抓取与规范化解析
2. 分组与稳定分配
3. Xray 配置渲染与报告输出
