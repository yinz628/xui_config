# X-UI Web Console Design

- 日期：2026-04-07
- 状态：Draft
- 范围：本 spec 只定义第一版 Web 控制台，用于管理订阅源、分组规则、触发生成、查看 report/state

## 1. 背景与目标

当前项目已经具备如下能力：

1. 读取 `mapping.yaml`
2. 拉取订阅并解析节点
3. 基于规则分组
4. 做稳定端口分配
5. 输出 `config.generated.json`
6. 输出 `config.generated.report.json`
7. 持久化 `state/port_bindings.json`

当前痛点是：

1. 日常操作仍以手改 YAML 为主
2. 订阅源和分组规则修改不够直观
3. 生成结果、问题和状态文件需要手动查看
4. Docker Compose 已能部署生成器，但缺少一个统一操作台

本次 Web 控制台的目标是：

1. 提供一个 Data-First 的后台界面
2. 让常见操作从“改文件”变成“改页面”
3. 保持现有生成核心逻辑不变
4. 与现有 `generator` 部署模型解耦

本 spec 的非目标：

1. 不做完整用户系统
2. 不做 SSH 运维平台
3. 不做 x-ui reload / VPS 部署按钮
4. 不做多用户协作和并发编辑控制
5. 不重写生成核心为全新服务

## 2. 产品方向

### 2.1 设计方向

后台采用 **B. Data-First** 方向。

核心原则：

1. 配置编辑优先
2. 生成结果紧随其后
3. 运维能力暂不前置

### 2.2 第一版范围

第一版只做到：

1. 配置管理
2. 一键生成
3. 查看 `report/state`

明确不做：

1. VPS 部署
2. 远程 `docker compose build/run`
3. x-ui / xray reload
4. 远端日志流

### 2.3 鉴权方式

采用**简单后台密码页**。

实现原则：

1. 单密码后台门禁
2. 服务端校验
3. 登录后写 session cookie
4. 未登录访问后台时统一跳转 `/login`

后台密码不写入 `mapping.yaml`，而是从环境变量读取。

## 3. 架构设计

### 3.1 服务拆分

第一版采用**独立 web 服务**。

系统拆分为：

1. `web` 服务
2. 现有 `generator core`
3. 现有 `generator` CLI/Compose 运行模型

### 3.2 `web` 服务职责

`web` 服务负责：

1. 提供登录页
2. 提供后台页面
3. 读写 `mapping.yaml`
4. 触发一次生成
5. 读取 `config.generated.report.json`
6. 读取 `state/port_bindings.json`

`web` 服务不负责：

1. 替代生成核心
2. 直接管理 VPS
3. 管理 x-ui 生命周期

### 3.3 生成逻辑复用

Web 不重写生成器逻辑。

生成动作由服务端直接调用现有核心：

- [pipeline.py](/F:/x-ui/xui_port_pool_generator/pipeline.py)

也就是说：

1. CLI 继续保留
2. Web 只是新增控制层
3. 文件产出和状态文件继续沿用现有路径

### 3.4 部署模型

Compose 最终形态变为：

1. `generator`
2. `web`

二者共享挂载目录：

1. `config/`
2. `data/`
3. `output/`

其中：

- `generator` 继续保留单次执行模型
- `web` 作为常驻服务提供后台页面

## 4. 页面信息架构

第一版页面固定为 6 个：

1. `/login`
2. `/dashboard`
3. `/sources`
4. `/groups`
5. `/generate`
6. `/reports`

### 4.1 Login

职责：

1. 输入后台密码
2. 登录成功后建立 session

不承担其他功能。

### 4.2 Dashboard

首页采用**直接可编辑型**。

首页内容建议为：

1. `sources` 快捷编辑区
2. 最近一次生成 summary
3. issue 数摘要
4. 组容量概览
5. 输出文件更新时间
6. 顶部主按钮：`保存`、`保存并生成`

首页不承载完整 groups 编辑，只放摘要和快捷入口。

### 4.3 Sources

完整编辑订阅源表。

字段：

1. `id`
2. `url`
3. `enabled`
4. `format`

操作：

1. 新增
2. 删除
3. 启停
4. 保存

### 4.4 Groups

`Groups` 页面采用**表格样式**。

主表字段：

1. `order`
2. `name`
3. `filter`
4. `exclude`
5. `port_range`
6. `source_ids`
7. `capacity usage`
8. `actions`

交互方式：

1. 主表负责展示摘要
2. 行内支持少量直接修改
3. 点击行后可展开详细编辑区
4. 支持验证范围冲突和正则格式

### 4.5 Generate

这一页只围绕一次生成动作展开。

内容：

1. 当前配置摘要
2. `Generate Now`
3. 执行中状态
4. 本次生成 summary
5. 最近 issues 预览
6. 输出文件入口

### 4.6 Reports

这一页专门看结果。

内容：

1. `config.generated.report.json` 摘要
2. issue 列表
3. `state/port_bindings.json` 的绑定概览
4. 每个 group 的端口占用

本页是诊断台，不是编辑页。

## 5. 交互与状态流

第一版采用同步流，不引入后台任务队列。

标准流程：

1. 用户访问后台
2. 未登录则跳 `/login`
3. 登录成功后进入后台
4. 页面编辑内存表单
5. 点击 `保存` 才落盘到 `mapping.yaml`
6. 点击 `保存并生成` 或 `Generate Now` 时同步调用生成逻辑
7. 生成完成后刷新 summary / report / state 展示

### 5.1 保存行为

`mapping.yaml` 是单一真实配置源。

页面只在明确保存时写回，不做隐式自动保存。

### 5.2 生成行为

生成动作为同步请求。

前端在生成期间展示：

1. running 状态
2. 按钮禁用
3. 完成后的 summary/issue 刷新

第一版不做：

1. 后台任务队列
2. WebSocket 日志流
3. 多生成任务并行

## 6. 后端接口边界

第一版后端只暴露 4 类能力：

### 6.1 Auth

1. 登录
2. 登出
3. session 检查

### 6.2 Config

1. 读取当前 `mapping.yaml`
2. 保存当前 `mapping.yaml`

### 6.3 Generate

1. 触发一次 `run_pipeline()`
2. 返回本次生成摘要

### 6.4 Results

1. 读取最新 report
2. 读取最新 state
3. 读取输出文件元信息

第一版不做通用开放 API，而是只做服务于后台页面的应用接口。

## 7. 技术约束

第一版建议固定为：

### 7.1 后端

`FastAPI`

### 7.2 模板

`Jinja2`

### 7.3 页面交互

`HTMX + 少量原生 JavaScript`

### 7.4 样式

首版使用手写 CSS，不引入重型 UI 框架。

### 7.5 存储

继续使用现有文件：

1. `mapping.yaml`
2. `config.generated.report.json`
3. `state/port_bindings.json`

### 7.6 密码配置

后台密码通过环境变量提供，例如：

`WEB_ADMIN_PASSWORD`

不写入 `mapping.yaml`、report 或 state。

## 8. 与现有部署的关系

Web 第一版不替代现有部署设计，而是在现有部署上追加一个控制层。

关系如下：

1. `generator` 仍可通过 CLI/Compose 单独运行
2. `web` 也可触发一次生成
3. 两者共享相同配置和输出目录

因此即使 Web 不可用：

1. CLI 仍可用
2. 定时任务仍可用
3. 部署资产仍可用

## 9. 最小验收标准

设计通过后，后续实现至少满足：

1. 用户能通过密码页登录后台
2. 能在页面中编辑并保存 `sources`
3. 能在页面中以表格方式编辑 `groups`
4. 能从页面触发一次生成
5. 能在页面中查看最近 report 摘要
6. 能在页面中查看 state 中的端口绑定情况
7. 不需要修改生成核心逻辑即可接入 Web
8. 不因为 Web 引入第二套配置源

## 10. 随后实现产物

该 spec 通过后，后续实现应至少产出：

1. `web` 服务代码
2. 登录页与 session 机制
3. Dashboard / Sources / Groups / Generate / Reports 页面
4. `docker-compose.yml` 中的 `web` 服务
5. Web 部署说明与环境变量说明
