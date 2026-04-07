# X-UI Generator Docker Compose Deployment Design

- 日期：2026-04-07
- 状态：Draft
- 范围：本 spec 只定义“生成器独立部署到 VPS，并以 Docker Compose 形式运行”的方案

## 1. 背景与目标

当前项目已经具备以下能力：

1. 读取 `mapping.yaml`
2. 拉取多个 Clash 订阅源
3. 基于规则分组节点
4. 做稳定端口分配
5. 生成 `config.generated.json`
6. 输出 `config.generated.report.json`
7. 持久化 `state/port_bindings.json`

本次部署设计的目标不是把 x-ui 一并容器化，而是把“配置生成器”独立部署到 VPS，并通过 Docker Compose 提供稳定、可重复、易回滚的运行方式。

本 spec 的直接目标：

1. 让生成器以容器方式在 VPS 上执行
2. 保证缓存、状态、输出结果都持久化
3. 保持生成器与 x-ui 的运行生命周期解耦
4. 为后续定时刷新和外部 reload 留出清晰边界

本 spec 的非目标：

1. 不把 x-ui 纳入同一个 Compose
2. 不直接管理 x-ui / xray 重载
3. 不定义 CI/CD
4. 不定义自动告警系统

## 2. 设计决策

### 2.1 部署形态

采用单服务 Docker Compose 方案，只部署一个 `generator` 服务。

`generator` 服务的职责：

1. 读取配置
2. 拉取订阅
3. 生成结果
4. 写入缓存、状态和报告

`generator` 服务不负责：

1. 启停 x-ui
2. 替换 x-ui 最终生效配置
3. 触发 x-ui 或 xray reload
4. 定时调度

结论：

生成器是编译器，不是控制面。

### 2.2 运行模式

首版采用“按需执行型”运行模式，而不是常驻 daemon。

推荐命令：

```bash
docker compose run --rm generator
```

原因：

1. 生成器本质上是单次任务
2. 执行完成即退出，更符合当前程序形态
3. 更容易和宿主机 `cron` 对接
4. 更容易排障和回滚

后续若需要定时刷新，应优先由宿主机调度：

```bash
docker compose run --rm generator
```

而不是先把调度逻辑写进应用进程。

### 2.3 宿主机目录布局

VPS 上推荐部署目录：

```text
/opt/xui-config/
  docker-compose.yml
  Dockerfile
  requirements.txt
  .env
  generate_xray_config.py
  xui_port_pool_generator/
  scripts/

  config/
    mapping.yaml
    config.json

  data/
    cache/
    state/

  output/
    config.generated.json
    config.generated.report.json
```

职责划分：

- `config/`：人工维护配置
- `data/cache/`：订阅缓存
- `data/state/`：稳定端口绑定状态
- `output/`：最终产出

### 2.4 挂载约定

容器内统一使用 Linux 路径：

- `/app/config/mapping.yaml`
- `/app/config/config.json`
- `/app/cache`
- `/app/state`
- `/app/output`

对应挂载关系：

- `./config:/app/config`
- `./data/cache:/app/cache`
- `./data/state:/app/state`
- `./output:/app/output`

重要约束：

线上 `mapping.yaml` 不能继续使用本地 Windows 示例路径，例如：

```yaml
url: file:///F:/x-ui/310config86-106.yaml
```

线上版必须改成：

1. 真实订阅 URL
2. 或容器内可访问的 Linux 本地路径

### 2.5 运行时路径约束

线上版 `mapping.yaml` 中 `runtime` 必须使用容器内路径：

```yaml
runtime:
  cache_dir: /app/cache
  state_path: /app/state/port_bindings.json
  output_path: /app/output/config.generated.json
  report_path: /app/output/config.generated.report.json
  output_mode: config_json
```

这是部署契约的一部分，不建议把这部分继续保留为开发机相对路径示例。

### 2.6 Compose 服务契约

推荐的 `docker-compose.yml` 语义如下：

```yaml
services:
  generator:
    build: .
    container_name: xui-config-generator
    working_dir: /app
    command:
      - python
      - generate_xray_config.py
      - --mapping
      - /app/config/mapping.yaml
      - --template
      - /app/config/config.json
    volumes:
      - ./config:/app/config
      - ./data/cache:/app/cache
      - ./data/state:/app/state
      - ./output:/app/output
    environment:
      PYTHONUNBUFFERED: "1"
```

实现层可根据需要补充：

1. `env_file`
2. 代理相关环境变量
3. `user`
4. `restart: "no"`

但首版不要求加入复杂编排。

### 2.7 容器镜像边界

镜像内只包含：

1. 应用代码
2. Python 运行时
3. Python 依赖

镜像内不应包含：

1. 订阅缓存
2. 运行时状态
3. 最终生成结果
4. VPS 特定机密配置

结论：

容器无状态，业务状态全部走挂载卷。

## 3. 部署流程

首版部署流程固定为以下步骤：

1. 在 VPS 上创建目录

```bash
mkdir -p /opt/xui-config/config
mkdir -p /opt/xui-config/data/cache
mkdir -p /opt/xui-config/data/state
mkdir -p /opt/xui-config/output
```

2. 部署代码到 `/opt/xui-config/`

3. 准备线上版 `config/mapping.yaml`

4. 准备线上版 `config/config.json`

5. 构建镜像

```bash
docker compose build
```

6. 执行一次生成

```bash
docker compose run --rm generator
```

7. 检查结果文件

```bash
ls -lah /opt/xui-config/output
ls -lah /opt/xui-config/data/state
```

## 4. Smoke 验证

仓库中的 smoke 样板：

- [test_smoke_connection.py](/F:/x-ui/scripts/test_smoke_connection.py)
- [test-smoke-connection.ps1](/F:/x-ui/scripts/test-smoke-connection.ps1)

定位为：

部署后的外部验收脚本，而不是容器启动流程的一部分。

首版 smoke 检查目标：

1. VPS 可 SSH 登录
2. 应用目录存在
3. `docker-compose.yml` 存在
4. `config/`、`data/`、`output/` 目录存在
5. `docker compose run --rm generator` 能成功执行
6. 生成结果文件能落盘

推荐在 smoke 脚本中执行的远端检查：

```bash
cd /opt/xui-config
docker compose run --rm generator
docker compose ps
ls -lah output
sed -n '1,80p' output/config.generated.report.json
```

不建议首版 smoke 直接检查 x-ui 内部状态，因为本次部署边界是“生成器独立运行”。

## 5. 运维边界

### 5.1 生成器负责

1. 抓取订阅
2. 解析节点
3. 分组
4. 稳定端口分配
5. 输出配置
6. 输出报告
7. 维护状态文件

### 5.2 外部运维负责

1. 调度执行 `docker compose run --rm generator`
2. 读取 `output/config.generated.report.json`
3. 将 `output/config.generated.json` 接入 x-ui 或 xray 实际生效配置
4. 触发 x-ui / xray reload
5. 失败告警与恢复

该边界必须保持清晰，不应在首版部署里混用。

## 6. 随后扩展顺序

建议按以下顺序演进：

1. 先跑通单次 Compose 生成
2. 再加宿主机 `cron`
3. 再加“生成后替换配置并 reload”的外部脚本
4. 最后才评估是否把 x-ui 纳入同一个 Compose

这样每一步都能独立验证并降低回归范围。

## 7. 最小验收标准

部署完成后，至少满足：

1. `docker compose build` 成功
2. `docker compose run --rm generator` 成功退出，exit code 为 `0`
3. `output/config.generated.json` 被生成
4. `output/config.generated.report.json` 被生成
5. `data/state/port_bindings.json` 被生成并持久化
6. 连续执行两次后，已有节点端口绑定不漂移
7. 遇到脏数据或未支持协议时，生成过程不会整体崩溃，而是写入 report

## 8. 后续实现产物

该 spec 通过后，下一步实现应至少产出：

1. `Dockerfile`
2. `docker-compose.yml`
3. `requirements.txt`
4. `.env.example`
5. 部署说明文档
6. 适配 VPS 路径的示例 `mapping.yaml`
