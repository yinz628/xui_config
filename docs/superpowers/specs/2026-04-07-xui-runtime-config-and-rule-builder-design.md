# X-UI Runtime Config and Rule Builder Design

- 日期：2026-04-07
- 状态：Draft
- 范围：本 spec 只扩展 Web 控制台的两项能力：运行态配置管理与 Rule Builder

## 1. 背景

当前 Web 控制台已具备：

1. 登录页
2. Sources 页面
3. Groups 页面
4. Generate 页面
5. Reports 页面
6. 一次生成触发
7. report/state 查看

但仍存在两个明显不足：

1. 运行态配置仍大量依赖 SSH 手工维护
2. Groups 仍然主要依赖 regex 文本，不够直观，无法方便地按地区和单节点做精细控制

因此需要新增：

1. `Runtime Config`
2. `Rule Builder`

## 2. 运行态配置管理

### 2.1 目标

把当前 VPS 上的运行态文件：

1. `/opt/xui-config/config/mapping.yaml`
2. `/opt/xui-config/config/config.json`

从“手工改文件”升级成“Web 控制台可视化管理”。

### 2.2 页面结构

新增一个页面：

- `/runtime-config`

### 2.3 页面职责

页面至少展示：

1. 当前 `mapping.yaml` 路径
2. 当前 `config.json` 路径
3. 文件大小
4. 最后修改时间

页面至少支持：

1. 查看当前运行态 `mapping.yaml`
2. 在线编辑并保存 `mapping.yaml`
3. 上传 YAML 文件替换 `mapping.yaml`
4. 查看当前运行态 `config.json`
5. 在线编辑并保存 `config.json`
6. 上传 JSON 文件替换 `config.json`

### 2.4 校验规则

保存 `mapping.yaml` 前必须：

1. 通过 YAML 语法校验
2. 通过现有 `load_mapping()` 结构校验

保存 `config.json` 前必须：

1. 通过 JSON 语法校验
2. 通过最小结构校验

最小结构至少检查：

1. `inbounds`
2. `outbounds`

### 2.5 示例配置对照

页面中建议同时展示：

1. 当前运行态配置
2. 示例模板文件

例如：

1. `config/mapping.vps.example.yaml`
2. `config/config.json.example`

这样用户能清楚区分“示例”与“当前真实运行态”。

## 3. Rule Builder

### 3.1 目标

将 Groups 从“纯 regex 配置”升级成“结构化规则 + 可视化节点选择”。

### 3.2 数据来源

Rule Builder 基于**最近一次生成快照**，而不是实时重新拉订阅。

建议新增快照文件：

- `output/nodes.snapshot.json`

该文件至少包含：

1. `node_uid`
2. `display_name`
3. `source_id`
4. `protocol`
5. `server`
6. `server_port`
7. `region_tags`
8. `matched_group`
9. `last_seen_at`

### 3.3 页面位置

Rule Builder 不建议独立成一个完全分离页面。

推荐方式：

- 作为 `Groups` 页面里某个组的详细编辑工作台

也就是：

1. `Groups` 页仍保留组表格
2. 点击某个组后，展开该组的 Rule Builder 面板

### 3.4 页面结构

Rule Builder 面板建议分 4 区：

1. 组信息区
2. 地区标签区
3. 节点快照表
4. 规则结果区

### 3.5 地区标签区

展示所有地区标签，例如：

- `HK`
- `US`
- `JP`
- `SG`
- `TW`
- `KR`

每个标签支持 3 态：

1. 未选择
2. 包含
3. 排除

页面需提供：

1. 全选
2. 反选
3. 清空

### 3.6 节点快照表

基于 `nodes.snapshot.json` 展示全部节点。

列建议至少包含：

1. 节点名
2. 地区
3. source
4. 协议
5. server
6. 端口
7. 当前命中状态

每行支持：

1. 手动包含
2. 手动排除
3. 清除手工覆盖

### 3.7 规则结果区

页面实时显示最终要保存的结构化规则，例如：

```yaml
include_regions: [hk, us, jp]
exclude_regions: [tw]
manual_include_nodes:
  - node_uid_1
manual_exclude_nodes:
  - node_uid_2
filter_regex: "(?i)(IEPL|家宽)"
exclude_regex: "(?i)(测试)"
```

用户无需手写 regex，也能明确知道最终保存内容。

## 4. 规则优先级

### 4.1 组内优先级

推荐优先级：

1. `manual_exclude_nodes`
2. `manual_include_nodes`
3. `include_regions`
4. `exclude_regions`
5. `filter_regex`
6. `exclude_regex`

解释：

1. 手工规则优先级最高
2. 地区规则用于大范围筛选
3. regex 用于细筛

### 4.2 组间优先级

组间仍保持：

- `first match wins`

也就是多个组同时命中时，按组顺序取第一个。

## 5. 建议的数据模型扩展

建议 `groups[]` 扩展为支持以下字段：

```yaml
groups:
  - name: tg_hk
    include_regions: [hk, jp]
    exclude_regions: [tw]
    manual_include_nodes: []
    manual_exclude_nodes: []
    filter_regex: ""
    exclude_regex: ""
    port_range:
      start: 20000
      end: 20199
```

兼容原则：

1. 保留现有 `filter`
2. 保留现有 `exclude`
3. 新字段逐步接入

### 5.1 推荐过渡方式

短期：

- 同时支持旧字段与新字段

长期：

- 页面主交互优先使用结构化字段

## 6. 最小实现顺序

推荐顺序：

1. 先实现 `Runtime Config`
2. 再实现 `nodes.snapshot.json`
3. 再实现 Rule Builder 的地区筛选
4. 再实现单节点手动 include/exclude
5. 最后再把 regex 细筛整合进 Rule Builder

## 7. 最小验收标准

设计通过后，后续实现至少满足：

1. 用户可在 Web 页面中查看当前运行态 `mapping.yaml` 与 `config.json`
2. 用户可在线编辑并保存运行态配置
3. 用户可上传 YAML/JSON 文件替换运行态配置
4. 每次生成后产出 `nodes.snapshot.json`
5. Groups 页面可基于节点快照进行地区筛选
6. Groups 页面可对单个节点做手工包含/排除
7. 页面中清晰展示规则优先级与最终规则结果

## 8. 后续实现产物

该 spec 通过后，后续实现应至少产出：

1. `Runtime Config` 页面
2. `nodes.snapshot.json` 生成逻辑
3. `Rule Builder` 面板
4. `mapping.yaml` 结构扩展与兼容逻辑
5. 对应测试与部署说明
