# mbuf 与 pktmbuf 分配路径

如果说 `mempool` 解决的是“对象从哪里来”，那 `mbuf` 解决的就是“包在 DPDK 里长什么样、一路怎么传”。

DPDK 里绝大部分收包、发包、转发、分类、封装、卸载，最后都要落到 `rte_mbuf` 这个结构上。理解了它，很多 API 看起来就不再是零散碎片。

---

## mbuf 不是单纯的 buffer

`rte_mbuf` 这个名字容易让人误会成“一个数据缓冲区”。其实它更像“包描述头 + 数据区入口 + 一堆元信息”。

一个典型的 packet mbuf 至少包含：

- `rte_mbuf` 头部
- 关联的 data buffer
- headroom
- data_off / data_len / pkt_len
- `next` 指针，用于多段包
- 各种 offload metadata

官方文档特别强调了一点：`rte_mbuf` 头部尽量控制在两个 cache line 内，而且最常用字段优先放在第一条 cache line 里。这是非常典型的数据面设计思路。

---

## 为什么元数据和数据区放在一起

官方文档提到过两种设计选择：

1. 元数据和数据区放在同一个对象里
2. 元数据和数据区完全拆开

DPDK 选了第一种。原因很现实：

- 分配/释放只要一次对象操作
- RX 收包时可以更直接地把 descriptor 指向 buffer
- 数据面路径里对象生命周期更简单

代价也有，就是灵活性不如完全拆开。但对以吞吐为优先级的数据面来说，这个取舍非常合理。

---

## 单段包与多段包

最简单的包就是单个 mbuf，头和数据都在一个对象里。

但现实里会遇到：

- jumbo frame
- TSO/GSO
- 某些零拷贝或外部 buffer 方案

这时一个包可能由多个 mbuf 串起来，通过 `next` 指针形成链表。

```mermaid
graph LR
    A["mbuf #0<br/>meta + data"] --> B["mbuf #1<br/>data segment"]
    B --> C["mbuf #2<br/>data segment"]
```

这里一个重要原则是：**整包级元信息通常只放在首段 mbuf 上。** 后续段更多只是承载数据。

---

## 从 pool 创建 pktmbuf

最常见的入口：

```c
struct rte_mempool *mp = rte_pktmbuf_pool_create(...);
```

这个接口本质上还是在建 `mempool`，只是它替你把对象布局准备好了：

- 前面放 `rte_mbuf`
- 后面放 data room
- 初始化固定字段
- 设定默认 headroom

因此 `pktmbuf pool` 不是另一种 allocator，而是“预配置成网络包对象格式的 mempool”。

---

## 分配路径

分配一个新包常见是：

```c
struct rte_mbuf *m = rte_pktmbuf_alloc(mp);
```

从行为上看，发生的事情大概是：

1. 从 mempool 拿一个对象
2. 还原/保留 constructor 已初始化好的固定字段
3. 设置成“单段、长度为 0、data_off 指到 headroom 后”的初始状态

这里有一个容易忽略的细节：**释放回 pool 时，对象内容不会被整体清零。**

所以那些一开始就固定的字段，例如来源 pool、buffer 起始位置，通常不需要每次分配时重建；而真正会变化的字段，如长度、链表关系、offload 标志，才需要按生命周期更新。

---

## headroom 的意义

新分配出来的 mbuf，`data_off` 默认不会指向 buffer 起点，而是往后留出一段 headroom。

这样做的主要目的是：

- 便于在包前 prepend L2/L3/L4 头
- 避免每次封装都重新分配对象

所以后面看 `rte_pktmbuf_prepend()`、`append()`、`adj()`、`trim()` 这类 API，就能理解它们其实是在管理“当前有效数据窗口”。

---

## RX 路径里 mbuf 是怎么来的

驱动初始化 RX queue 时，会先从某个 pktmbuf pool 申请一批 mbuf，把它们的 buffer 地址填进 RX descriptor。

收包之后，NIC 往这些 buffer 里 DMA 数据；驱动在 `rte_eth_rx_burst()` 里做的主要事情是：

- 从已完成 descriptor 里取回对应 mbuf
- 更新 `data_len` / `pkt_len` / `port` / `ol_flags` 等元信息
- 把新的空 mbuf 再补回 RX ring

所以 RX 快路径里最核心的对象流转，实际上就是：

```text
mempool -> RX descriptor -> NIC DMA -> mbuf 返回给应用 -> 新 mbuf refill
```

---

## TX 路径里 mbuf 什么时候释放

这个问题新手很容易想当然：“调用 `rte_eth_tx_burst()` 成功发出去，不就该立刻 free 吗？”

实际不是。

很多驱动会把 mbuf 暂时挂在 TX ring 对应 descriptor 上，等硬件真正完成发送并回写状态后，再批量回收。这也是为什么文档里会单独提 `tx_free_thresh`、`tx_rs_thresh`。

换句话说，TX 成功 enqueue 到 NIC queue，不等于 mbuf 当场回到 mempool。

---

## indirect buffer 与 clone

`mbuf` 还有一套很实用的能力：direct / indirect buffer。

- direct buffer：自己拥有数据区
- indirect buffer：元数据是自己的，但数据区引用别人的

这对包复制、镜像、分片、重组都很有用。因为复制一个大包最贵的不是元数据，而是数据本体；如果能共享 data buffer，只增加引用计数，代价就小很多。

不过 indirect buffer 也带来更严格的生命周期约束。最稳妥的做法通常是优先用官方提供的 clone/attach API，而不是手动拼字段。

---

## offload 元数据为什么这么多

很多第一次看 `rte_mbuf` 的人都会被 `ol_flags`、`l2_len`、`l3_len`、`l4_len`、`outer_l2_len` 这堆字段吓到。

这些字段存在的原因是：**DPDK 想把“要不要让硬件帮我做事”这个决策，编码到每个包上。**

例如：

- IP/TCP/UDP checksum offload
- TSO
- tunnel 场景下 inner / outer header 长度
- RSS hash、VLAN、timestamp 等 RX metadata

所以 `mbuf` 其实不只是包容器，还是应用与驱动之间传递 per-packet 指令的载体。

---

## 动态字段与动态 flag

官方文档后来补充了 `rte_mbuf_dyn*` 这套机制，本质上是承认一个现实：固定的 `rte_mbuf` 头再怎么设计，也不可能提前预留所有未来特性。

所以 DPDK 提供了动态字段和动态 flag：

- 允许库/驱动在 mbuf 的动态区域注册额外空间
- 避免每加一个功能就把 `struct rte_mbuf` 硬编码得更臃肿

这对扩展性很好，但也意味着工程里要管理好“哪些组件注册了哪些字段”，否则排查问题会比较痛苦。

---

## 调试时的几个抓手

`mbuf` 一旦损坏，症状通常特别飘：

- 某个包莫名其妙长度异常
- 链表断掉
- free 时崩溃
- 驱动报 descriptor 错误

这时可以借助：

- `RTE_LIBRTE_MBUF_DEBUG`
- assert
- mbuf history

尤其是 `mbuf history`，适合抓“这个包到底在哪条路径被改坏了”。

---

## 实战里最常见的误区

### 1. 忘了 TX 成功不等于立即回收

结果 pool 很快被耗尽，以为是泄漏，实际上是 TX recycle 阈值和发送节奏没配好。

### 2. 修改了首段外的元信息

对多段包来说，很多字段只应该在首段上维护。

### 3. 盲目 clone / attach

引用计数和 direct/indirect 关系稍微处理错一点，后果通常是双重释放或者悬挂引用。

### 4. 忽略 headroom/tailroom

封装、去封装、prepend、trim 这些操作都在吃这个窗口，空间不够时不能硬写。

---

## 一个最朴素的理解

`rte_mbuf` 可以看成 DPDK 里的“包对象协议”。

只要一个组件说“我处理的是包”，基本就默认它输入输出都是 mbuf。驱动填它、协议栈改它、分类器读它、offload 根据它做事，最后回收也通过它回到 mempool。

所以 `mbuf` 并不只是某个数据结构，而是整个数据面最核心的交换格式。
