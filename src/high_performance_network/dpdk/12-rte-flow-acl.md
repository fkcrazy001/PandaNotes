# flow/ACL 规则下发

DPDK 里“规则”这件事至少有两条很常见的路：

- `rte_flow`：尽量把匹配和动作下推给 NIC / PMD
- ACL：在 CPU 上做软件分类

这两者经常被一起提，但定位其实不一样。一个偏设备侧 offload，一个偏软件侧匹配引擎。工程里最容易犯的错，就是把它们混成一件事。

---

## `rte_flow` 想解决什么

官方文档对 `rte_flow` 的定义很准确：提供一种通用方式，让应用描述“匹配什么流量，对命中的流量做什么动作，并且能查询相关计数”。

它的核心价值是把过去厂商私有、寄存器风格很强的硬件流表能力，抽象成统一接口：

- match
- action
- priority
- group
- query

所以 `rte_flow` 不是某个库的小功能，而是 DPDK 在硬件流表抽象上的正统入口。

---

## 一条 flow rule 由什么组成

一条规则由三部分构成：

- `attr`
- `pattern`
- `actions`

```mermaid
flowchart LR
    A["attr<br/>方向 / group / priority / transfer"] --> B["pattern<br/>一串 rte_flow_item"]
    B --> C["actions<br/>QUEUE / DROP / RSS / MARK / JUMP ..."]
```

这个结构和很多硬件 pipeline 的思维方式非常接近：先决定表在哪一层，再描述匹配条件，最后描述命中动作。

---

## pattern 为什么要按协议栈顺序堆

`rte_flow_item` 不是随便列的。官方文档要求匹配项大体按协议层级从低到高堆起来：

- Ethernet
- IPv4/IPv6
- TCP/UDP
- Tunnel
- Inner headers

这背后的原因很简单：大多数硬件匹配器本来就是按协议头层级解析的。DPDK 不想假装自己比硬件更抽象，所以 pattern 结构直接顺着硬件思维来。

这也是为什么像“L2 后面直接跟 UDP，没有 L3”这样的 pattern，会被视为不合法。

---

## group 与 priority

这是 `rte_flow` 最容易被低估的两层语义。

### priority

在同一个 group 里，数字越小优先级越高。

但官方也明确提醒：**不能假设硬件一定支持很多优先级层级。** 很多设备优先级层数很少，甚至需要 PMD 自己做部分软件模拟。

### group

group 更像逻辑表。默认只有 group 0 一定会被命中，其他 group 要靠 `JUMP` 动作显式进入。

这说明 group 不是“给规则分类做标签”，而是真正的 pipeline 结构。

---

## validate 很重要

`rte_flow` 最大的难点之一，是“支持哪些 pattern/action 组合”高度依赖具体 PMD 和设备状态。

官方没有试图提前给一个巨大的 capability matrix，而是提供了 `validate` 思路：**把你准备下发的规则，先拿当前设备状态去验一次。**

这在工程上非常合理，因为：

- queue 还没建好时，某些 QUEUE action 本来就不该成功
- 某些 tunnel / mark / meter 组合只在特定设备支持
- 某些 rule overlap 在同一优先级下会被拒绝

所以靠谱流程通常是：`validate -> create -> query/destroy`，而不是直接 create 再赌。

---

## transfer flow

`transfer` 属性特别值得单独提一下。它表示规则不是只从“当前 port 视角的 ingress/egress”去看，而是尽量下推到设备内部更低层的转发表里。

这在 representor、switchdev、eswitch 相关场景非常关键。也说明 `rte_flow` 不只是端口级过滤器，而是能触到更靠近交换芯片/嵌入式交换流水线的层面。

---

## 动作组合为什么复杂

早期做硬件流表的人常把一条规则理解成“match -> one action”。但 `rte_flow` 从一开始就允许多动作组合，例如：

- count
- mark
- decap
- encap
- jump
- queue / rss / port redirect

这很像告诉应用：不要替硬件做过度拆分，一条规则能完成的事情，就尽量一次描述清楚。

当然，代价是不同 PMD 对动作顺序和组合的支持度差异更大。

---

## 错误报告为什么单独成章

官方给 `verbose error reporting` 单独留了一节，是很对的。因为 `rte_flow_create()` 失败时，如果只有一个 `-EINVAL`，几乎没法排查。

`rte_flow_error` 里至少会告诉你：

- 错在哪一类对象
- 是 attr / item / action 的问题
- 某些情况下还有更具体的 message

工程里写 flow 下发代码时，这个错误结构一定要完整打印出来，不然 debug 成本非常高。

---

## ACL 应该放在哪个位置理解

ACL 和 `rte_flow` 经常同章出现，是因为它们都属于“分类”。但差别非常大：

- `rte_flow`：尽量让 NIC / PMD 替你分类并执行动作
- ACL：数据还在 CPU 手里，由软件分类器匹配

所以更实用的边界是：

- 能稳定硬件下推的，优先 `rte_flow`
- 硬件不支持、规则组合太复杂、或者更需要软件灵活性的，用 ACL

从这个角度看，ACL 更像 fallback 或补充，而不是 `rte_flow` 的同义词。

---

## 常见坑

### 1. 不做 validate 就直接 create

配置顺序稍微不对就会踩坑。

### 2. 把 group 当普通标签

它更像流表层级，不是随便分类。

### 3. 假设所有设备都支持复杂动作链

`rte_flow` 是统一接口，不是统一能力。

### 4. 错误信息没打印全

这是排 flow 问题最浪费时间的地方。

---

## 一个工程上的经验

如果把 `rte_flow` 当成“通用硬件 pipeline 描述语言”，很多设计就顺了：

- attr 决定表上下文
- pattern 决定匹配
- action 决定命中后去向

而 ACL 则更像软件侧保底分类器。两者一起用时，才比较接近真实系统的完整分类策略。
