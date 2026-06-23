# dpdk

DPDK 专栏，基于官方 `Programmer's Guide` 和部分 `HowTo` 文档，再结合代码路径去看实现细节。

我自己更关心的不是“API 有什么”，而是“它为什么要这么设计”、“热路径到底在哪里”、“哪些抽象在真实工程里最容易漏掉”。所以这些章节不会逐段翻译官方文档，而是按工程上真正会遇到的问题来组织。

## 章节目录

- [01：EAL 初始化与 lcore/线程模型](./01-eal-init-lcore.md)
- [02：Hugepage/内存子系统](./02-hugepage-memory.md)
- [03：mempool 机制](./03-mempool.md)
- [04：mbuf 与 pktmbuf 分配路径](./04-mbuf-pktmbuf.md)
- [05：ring / rte_ring](./05-rte-ring.md)
- [06：ethdev 抽象](./06-ethdev.md)
- [07：PMD 驱动加载与探测](./07-pmd-probe.md)
- [08：RX/TX 数据通路](./08-rx-tx-datapath.md)
- [09：multi-process 与 IPC](./09-multi-process-ipc.md)
- [10：service cores 与调度](./10-service-cores.md)
- [11：telemetry / stats / debug](./11-telemetry-stats-debug.md)
- [12：flow/ACL 规则下发](./12-rte-flow-acl.md)
- [13：vhost-user / virtio-user](./13-vhost-virtio-user.md)
- [14：性能调优方法论](./14-performance-tuning.md)

## 附录

- [LPM 算法](./lpm.md)
- [mlx5 驱动](./mlx5_core.md)
