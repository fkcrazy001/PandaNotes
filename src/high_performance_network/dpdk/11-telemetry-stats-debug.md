# telemetry / stats / debug

DPDK 的数据面经常给人一种“跑起来就很快，但出了问题很难看”的印象。其实官方这些年把可观测性补得已经比早期好很多了，至少有三条常用路径：

- `stats / xstats`
- telemetry
- log / trace / debug 工具

真正工程里排问题，通常不会只靠其中一个。

---

## telemetry 是什么

telemetry 本质上是一个 JSON over Unix socket 的查询接口。应用启动后，Telemetry library 会打开一个 socket，外部客户端连进来发命令，DPDK 返回结构化数据。

它的定位不是“高频监控采样总线”，而是“统一把库和应用内部状态暴露出来”。

---

## 为什么它好用

传统 DPDK 排障常见两种方式：

- 打日志
- 在应用里额外加命令行/CLI

telemetry 的好处是把很多通用信息统一收敛进一条接口：

- ethdev 端口列表
- link status
- xstats
- EAL 参数
- 应用自定义命令

于是“看运行时状态”这件事不用每个项目都重新造一套轮子。

---

## 使用方式

官方文档对应的交互很直接：

1. 启动一个 DPDK 应用
2. 用 `dpdk-telemetry.py` 连到 telemetry socket
3. 输入命令，得到 JSON 返回

典型命令比如：

```text
/
/ethdev/list
/ethdev/xstats,0
/help,/ethdev/xstats
```

这里一个细节很好用：命令参数是用逗号拼进请求字符串里的，所以一些简单查询非常轻量。

---

## socket 路径与 file-prefix

telemetry socket 会落在运行时目录里，路径和 `file-prefix`、实例编号有关系。

这和 multi-process 那一章其实是连着的：如果你有多个 DPDK 实例并排跑，想连对 telemetry socket，就得明确：

- 是哪个 `file-prefix`
- 是第几个 instance

否则你看到的根本不是你以为的那个进程。

---

## 应用怎么注册自己的 telemetry 命令

Telemetry library 提供的是 callback 注册框架。库或应用要暴露信息，通常要做两件事：

1. 写一个 `telemetry_cb`
2. 用 `rte_telemetry_register_cmd()` 注册命令

callback 收到：

- `cmd`
- `params`
- `struct rte_tel_data *`

然后把结果写进 `rte_tel_data`，库再统一格式化成 JSON。

这套接口很像“轻量 RPC handler”，只是 transport 固定成了本地 Unix socket。

---

## `rte_tel_data` 的三种常见组织方式

官方文档展示了三类最常用的数据形态：

- array
- dict
- string

这个设计很克制，但够用了。多数运维/排障场景要么看列表，要么看 key/value，要么看一段状态文本，不需要更复杂的 schema 系统。

---

## `stats` 与 `xstats` 的分工

除了 telemetry，ethdev 自己还有 stats 接口。

- `stats`：更通用，适合跨设备比较
- `xstats`：更细，更贴近驱动/硬件细节

真正排丢包时，xstats 的信息量往往明显更高。因为很多关键异常，例如：

- missed packets
- queue drops
- pause / PFC 计数
- checksum / descriptor error

常常都藏在扩展计数器里。

---

## log、trace、debug 不是一回事

这三样最好分开理解：

### log

更适合状态变化、错误路径、启动配置。

### trace

更适合观察运行时事件流，粒度比普通日志细，但通常也更贵。

### debug 开关

更像编译时/运行时的额外校验，比如 mempool cookie、mbuf sanity check。

它们解决的问题不同，别指望只开一种就把所有问题看清。

---

## telemetry 与 debug 的边界

telemetry 更像“读状态”，而 debug 更像“抓错误”。

例如：

- 想看当前有哪些端口、queue 统计是多少，用 telemetry
- 想确认某类 mbuf 有没有被写坏，用 mbuf debug/history
- 想看 service core 或线程状态变化，用 trace

这几条链路互补，而不是互相替代。

---

## 常见坑

### 1. 只看总包量，不看 xstats

很多真正有价值的硬件异常信息都在扩展计数器里。

### 2. 多实例场景连错 telemetry socket

尤其用了不同 `file-prefix` 或 `--in-memory` 后，这个问题非常常见。

### 3. callback 里做太重的事情

telemetry callback 更适合轻量查询，不适合顺手做复杂控制逻辑。

### 4. 线上长期开很重的 debug 校验

能查问题，但也可能直接把热路径性能打下来。

---

## 一个更实用的排障思路

我自己更倾向于把 DPDK 可观测性分成三层：

- 第一层：`stats/xstats` 看设备健康
- 第二层：telemetry 看库和应用运行态
- 第三层：log/trace/debug 抓时序和异常

这样排问题时就不容易东一榔头西一棒子。先判断“是设备问题、资源问题还是代码路径问题”，再决定该看哪条链路。
