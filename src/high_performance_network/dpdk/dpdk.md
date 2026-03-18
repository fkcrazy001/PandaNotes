# dpdk

DPDK 专栏，基于 官方 <http://doc.dpdk.org/guides/prog_guide/> 的 program guide，从代码中验证相关实现细节。

官方文档中的每一个章节，会有相应的技术实现细节。

## 章节目录（Draft）

- [00：专栏导读与阅读方法](./00-reading-guide.md)
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

## 实现进度（手工维护）

状态枚举：
- 未开始：仅有章节骨架
- 进行中：正在阅读源码/补图/补验证
- 已完成：主流程 + 关键数据结构 + 可复现验证已补齐
- 待重构：内容需要重写/拆分/补证据链

| 章节 | 状态 | 里程碑/完成度 | 备注（代码阅读路径/关键点） | 最后更新 |
|---|---|---:|---|---|
| 00：专栏导读与阅读方法 | 已完成 | 100% | 建立 Program Guide ↔ `/home/panda/dpdk` 源码映射与写作模板 | 2026-03-16 |
| 01：EAL 初始化与 lcore/线程模型 | 已完成 | 100% | `lib/eal/linux/eal.c:rte_eal_init()`、IOVA 选择、bus scan | 2026-03-16 |
| 02：Hugepage/内存子系统 | 已完成 | 100% | `lib/eal/common/eal_common_memory.c`：memseg_list/virt↔iova | 2026-03-16 |
| 03：mempool 机制 | 已完成 | 100% | `lib/mempool/rte_mempool.c`：ops 选择、per-lcore cache、cookies | 2026-03-16 |
| 04：mbuf 与 pktmbuf 分配路径 | 已完成 | 100% | `lib/mbuf/rte_mbuf.c`：pool_create/extbuf/sanity check | 2026-03-16 |
| 05：ring / rte_ring | 已完成 | 100% | `lib/ring/rte_ring_core.h` + `lib/ring/rte_ring.c`：head/tail、flags | 2026-03-16 |
| 06：ethdev 抽象 | 已完成 | 100% | `lib/ethdev/rte_ethdev.c`：`rte_eth_devices[]`、`rte_eth_fp_ops[]` | 2026-03-16 |
| 07：PMD 驱动加载与探测 | 已完成 | 100% | `lib/eal/common/eal_common_bus.c` + `drivers/bus/pci/*` | 2026-03-16 |
| 08：RX/TX 数据通路 | 已完成 | 100% | ethdev fp_ops → PMD `rx_burst/tx_burst`；offload 传递链路 | 2026-03-16 |
| 09：multi-process 与 IPC | 已完成 | 100% | `lib/eal/common/eal_common_proc.c`：UDS + SCM_RIGHTS + mp-msg thread | 2026-03-16 |
| 10：service cores 与调度 | 已完成 | 100% | `lib/eal/common/rte_service.c`：register/runstate/stats；示例 `examples/service_cores` | 2026-03-16 |
| 11：telemetry / stats / debug | 已完成 | 100% | `lib/telemetry/*`、`lib/metrics/*telemetry*`、ethdev stats/xstats | 2026-03-16 |
| 12：flow/ACL 规则下发 | 已完成 | 100% | `lib/ethdev/rte_flow.c/h` + `examples/flow_filtering` + PMD flow 实现 | 2026-03-16 |
| 13：vhost-user / virtio-user | 已完成 | 100% | `lib/vhost/*`：register、协议处理、vring 数据面；示例 `examples/vhost` | 2026-03-16 |
| 14：性能调优方法论 | 已完成 | 100% | pinning/NUMA → mempool/ring/mbuf → queue/RSS → offload → profiling | 2026-03-16 |
