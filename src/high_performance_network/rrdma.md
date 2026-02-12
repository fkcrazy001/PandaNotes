# RRDMA

实现一个自己的 RDMA 虚拟网卡，纯软件模拟，基于 Rust 开发。类似 soft-roce，让普通以太网卡支持 RDMA/RoCE 协议。

## 技术选型

| 方案 | 选择 | 理由 |
|------|------|------|
| io_uring 用户态 | ✅ | 开发效率高、调试容易、生态成熟 |
| Rust 内核模块 | ⏸️ 待研究 | 研究价值高，但开发周期长 |

---

# 阶段一：Rust io_uring 基础操作

## 目标

掌握 io_uring 的基本使用，能够进行异步 I/O 操作。

## 学习路线

```
1. io_uring 概念入门
   └── 理解 SQ (Submit Queue) 和 CQ (Completion Queue)
   └── 理解 SQE (Submission Queue Entry) 和 CQE (Completion Queue Entry)
   
2. 基础 API 使用
   ├── 使用 io-uring crate 进行文件读写
   ├── 使用 tokio-uring 进行异步编程
   └── 理解 registered buffers 和 fixed files
   
3. 网络 I/O
   ├── UDP socket 收发
   └── 多队列和批量操作
```

## 参考资源

### 官方文档和教程

| 资源 | 链接 | 说明 |
|------|------|------|
| io-uring crate | https://docs.rs/io-uring/latest/io_uring/ | Rust io_uring 的官方 crate |
| tokio-uring | https://docs.rs/tokio-uring/latest/tokio_uring/ | Tokio 集成 io_uring |
| io_uring 官方文档 | https://unixism.net/2020/04/io-uring-by-example-1-introduction-to-io_uring/ | 完整的 io_uring 教程系列 |

### 开源示例

| 资源 | 链接 | 说明 |
|------|------|------|
| uring_examples | https://github.com/espoal/uring_examples | Rust io_uring 示例集 |
| uring-fs | https://docs.rs/uring-fs/latest/ | 异步文件系统操作 |
| tokio-uring 博客 | http://developerlife.com/2024/05/25/tokio-uring-exploration-rust/ | 详细的中文教程 |

### 关键概念

**1. 提交队列 (Submit Queue)**
- 应用提交 I/O 请求的地方
- SQE 包含操作类型、缓冲区指针、用户数据等

**2. 完成队列 (Completion Queue)**
- 内核返回 I/O 完成状态的地方
- CQE 包含结果状态、用户数据等

**3. Registered Buffers**
- 预先注册内存到内核，避免每次 I/O 拷贝
- 零拷贝发送的关键

**4. Fixed Files**
- 预先注册文件描述符，减少系统调用开销

## 实践任务

| 序号 | 任务 | 验收标准 |
|------|------|----------|
| 1.1 | 安装 liburing 开发库 | `apt install liburing-dev` 成功 |
| 1.2 | 编译运行 io-uring 示例 | 文件读取成功 |
| 1.3 | 使用 tokio-uring 重写 | 异步读取文件 |
| 1.4 | UDP echo server | 能收发 UDP 包 |
| 1.5 | 使用 registered buffers | 实现零拷贝发送 |

## 阶段一检查点

- [ ] 理解 io_uring 的工作原理
- [ ] 能用 io-uring crate 进行文件读写
- [ ] 能用 tokio-uring 进行异步编程
- [ ] 能用 UDP socket 收发数据
- [ ] 理解 registered buffers 的使用场景

---

# 阶段二：基于 Rust 的 RoCEv2 协议实现

## 目标

实现完整的 RoCEv2 协议栈，包括 IB 传输层、UDP/IP 封装、以太网帧。

## RoCEv2 协议栈结构

```
┌─────────────────────────────────────────────────────────────┐
│                      应用层 (Verbs)                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    IB 传输层 (L4)                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   BTH    │  │   RETH   │  │   AETH   │  │   DETH   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│   - opcode   │  - va      │  - syndrome│  - q_key   │       │
│   - dest_qp  │  - rkey    │  - msn     │  - src_qp  │       │
│   - psn      │  - length  │            │             │       │
│   - ack_req  │            │            │             │       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    UDP 层 (L3)                               │
│  - Source Port: 散列算法计算 (entropy)                      │
│  - Dest Port: 4791 (RoCEv2 标准端口)                        │
│  - Checksum: RoCEv2 必须为 0                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    IP 层 (L3)                                │
│  - IPv4 或 IPv6                                              │
│  - TTL/Hop Limit                                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    以太网层 (L2)                              │
│  - EtherType: 0x8915 (RoCE)                                 │
│  - MAC 地址                                                 │
└─────────────────────────────────────────────────────────────┘
```

## 参考资源

### 协议规范

| 资源 | 链接 | 说明 |
|------|------|------|
| IB Spec Annex A17 RoCEv2 | https://www.scribd.com/document/350043431/Annex17-RoCEv2 | 官方 RoCEv2 规范 |
| RoCEv2 Protocol 详解 | https://qsysarch.com/posts/the-infiniband-transport-protocol-of-rocev2/ | IB 传输层详解 |
| Nvidia RoCEv2 文档 | https://docs.nvidia.com/networking/display/winofv55053000/rocev2 | 厂商实现文档 |
| Broadcom RoCEv2 CNP | https://docs.broadcom.com/doc/NCC-WP1XX | 拥塞控制说明 |
| Netdev RoCEv2 介绍 | https://netdevconf.org/0x19/docs/netdev-0x19-paper18-talk-slides/netdev-0x19-AI-networking-RoCE-and-netdev.pdf | 协议概览 |

### 协议头部格式

**BTH (Base Transport Header) - 12 bytes**
| 字段 | 位数 | 说明 |
|------|------|------|
| Opcode | 8 | 操作码 (Send/Recv/RDMA Write/RDMA Read) |
| Solicited Event | 1 | 是否请求事件 |
| Mig Req | 1 | 迁移请求 |
| Pad Count | 3 | 填充字节数 |
| Transport Version | 3 | 传输版本 |
| P_Key | 16 | 分区密钥 |
| Reserved | 8 | 保留 |
| Dest QP | 24 | 目标队列对编号 |
| Ack Req | 1 | 请求确认 |
| PSN | 24 | 包序列号 |

**AETH (Ack Extended Transport Header) - 4 bytes**
| 字段 | 位数 | 说明 |
|------|------|------|
| Syndrome | 8 | 0=ACK, 1=NACK, 3=RNR NACK |
| MSN | 24 | 消息序列号 |

**RETH (RDMA Extended Transport Header) - 16 bytes)**
| 字段 | 位数 | 说明 |
|------|------|------|
| Virtual Address | 64 | 远程虚拟地址 |
| Remote Key | 32 | 远程访问密钥 |
| Length | 32 | 数据长度 |

**UDP 封装规则**
- 目的端口: 4791 (标准 RoCEv2 端口)
- 源端口: `(SrcPort XOR DstPort) OR 0xC000` 计算
- 校验和: 必须设置为 0 (RoCEv2 要求)

## 开源参考实现

| 资源 | 链接 | 说明 |
|------|------|------|
| Alex Forencich UDP/IP Stack | https://github.com/alexforencich/verilog-ethernet | FPGA 实现的以太网栈，包含 RoCEv2 参考 |
| RoCEv2 FPGA Parser | https://www.mdpi.com/2079-9292/13/20/4107 | 学术论文中的 RoCEv2 实现 |
| soft-roce 源码 | https://github.com/SoftRoCE/rxe-rdma-kernel | C 实现的 RDMA 软件模拟 |

## 实践任务

| 序号 | 任务 | 验收标准 |
|------|------|----------|
| 2.1 | 实现 BTH 头部 | 序列化/反序列化正确 |
| 2.2 | 实现 AETH 头部 | ACK/NACK 构造正确 |
| 2.3 | 实现 RETH 头部 | RDMA Read/Write 支持 |
| 2.4 | 实现 UDP 封装 | UDP 端口 4791，校验和为 0 |
| 2.5 | 实现 IP 封装 | IPv4 头部构造正确 |
| 2.6 | 实现以太网帧 | EtherType 0x8915 |
| 2.7 | 完整报文构造 | Wireshark 能解析 |

## 阶段二检查点

- [ ] 理解 RoCEv2 协议栈各层
- [ ] 能正确构造 BTH/AETH/RETH 头部
- [ ] 能构造完整的 RoCEv2 报文
- [ ] Wireshark 能正确识别报文格式
- [ ] 实现 UDP 校验和为 0 的规则

---

# 阶段三：ibverbs API 实现

## 目标

实现完整的 RDMA Verbs API，包括 Protection Domain、Memory Region、Completion Queue、Queue Pair 等核心概念。

## RDMA 核心概念

```
┌─────────────────────────────────────────────────────────────────┐
│                      RDMA 资源层次结构                           │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                    Context (设备上下文)                    │  │
│   │   - 代表一个 RDMA 设备                                    │  │
│   │   - 管理所有资源的生命周期                                 │  │
│   └─────────────────────────────────────────────────────────┘  │
│                              │                                 │
│              ┌───────────────┼───────────────┐                │
│              ▼               ▼               ▼                │
│   ┌─────────────────┐ ┌───────────────┐ ┌─────────────────┐    │
│   │ Protection      │ │ Completion    │ │      QP         │    │
│   │ Domain (PD)     │ │ Queue (CQ)    │ │  (Queue Pair)  │    │
│   │                 │ │               │ │                │    │
│   │ - 内存隔离       │ │ - 异步通知    │ │  - SQ (发送)   │    │
│   │ - 访问控制       │ │ - 完成事件    │ │  - RQ (接收)   │    │
│   └─────────────────┘ └───────────────┘ └─────────────────┘    │
│                              │                                 │
│                              ▼                                 │
│                    ┌─────────────────┐                          │
│                    │ Memory Region   │                          │
│                    │ (MR)            │                          │
│                    │                 │                          │
│                    │ - lkey (本地)   │                          │
│                    │ - rkey (远程)   │                          │
│                    │ - VA (虚拟地址)  │                          │
│                    │ - Length        │                          │
│                    └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

## QP 状态机

```
     ┌─────────────────────────────────────────────────────────────┐
     │                    QP 状态机                               │
     │                                                              │
     │   RESET ──────► INIT ──────► RTR ──────► RTS               │
     │      │            │            │            │              │
     │      │            │            │            │              │
     │      ▼            ▼            ▼            ▼              │
     │    ERROR       ERROR         ERROR        ERROR           │
     │                                              │             │
     │                                              ▼             │
     │                                           CLOSING          │
     │                                              │             │
     │                                              ▼             │
     │                                           ERROR            │
     └─────────────────────────────────────────────────────────────┘
     
     状态说明:
     - RESET: 初始状态，QP 不可用
     - INIT: 已初始化，可以接收 RTR 请求
     - RTR (Ready to Receive): 可以接收数据
     - RTS (Ready to Send): 可以发送数据
```

## 参考资源

### Rust ibverbs 库

| 资源 | 链接 | 说明 |
|------|------|------|
| rust-ibverbs | https://github.com/jonhoo/rust-ibverbs | 最流行的 Rust ibverbs 绑定 (197 ⭐) |
| safeverbs | https://github.com/crazyboycjr/safeverbs | 内存安全的 RDMA API (1 ⭐) |
| rdma-rs | https://github.com/phoenix-dataplane/rdma-rs | Rust RDMA 包装器 (2 ⭐) |
| rdma-sys | https://github.com/datenlord/rdma-sys | RDMA FFI 绑定 (49 ⭐) |
| async-rdma | https://github.com/datenlord/async-rdma | 异步 RDMA 框架 (163 ⭐) |
| rdma-cm | https://github.com/akshayknarayan/rdma-cm | RDMA CM 绑定 (1 ⭐) |

### ibverbs 官方文档

| 资源 | 链接 | 说明 |
|------|------|------|
| ibverbs crate docs | https://docs.rs/crate/ibverbs/latest | Rust 绑定文档 |
| IB Spec Verbs | https://www.infiniband.org/specs/ | 官方 IB 规范第 11 章 |
| RDMAmojo | https://www.rdmamojo.com/ | RDMA 教程网站 |

### 核心 API

**Protection Domain (PD)**
```c
// C API
struct ibv_pd *ibv_alloc_pd(struct ibv_context *context);
int ibv_dealloc_pd(struct ibv_pd *pd);
```

**Memory Region (MR)**
```c
// C API
struct ibv_mr *ibv_reg_mr(struct ibv_pd *pd, void *addr, size_t length,
                          int access);
int ibv_dereg_mr(struct ibv_mr *mr);
```

**Completion Queue (CQ)**
```c
// C API
struct ibv_cq *ibv_create_cq(struct ibv_context *context, int cqe,
                             void *cq_context, struct ibv_comp_channel *channel,
                             int comp_vector);
int ibv_destroy_cq(struct ibv_cq *cq);
int ibv_poll_cq(struct ibv_cq *cq, int num, struct ibv_wc *wc);
int ibv_req_notify_cq(struct ibv_cq *cq, int solicited_only);
```

**Queue Pair (QP)**
```c
// C API
struct ibv_qp *ibv_create_qp(struct ibv_pd *pd, struct ibv_qp_init_attr *attr);
int ibv_destroy_qp(struct ibv_qp *qp);
int ibv_modify_qp(struct ibv_qp *qp, struct ibv_qp_attr *attr,
                  int attr_mask);
```

**Work Request (WR)**
```c
// C API
int ibv_post_send(struct ibv_qp *qp, struct ibv_send_wr *wr,
                  struct ibv_send_wr **bad_wr);
int ibv_post_recv(struct ibv_qp *qp, struct ibv_recv_wr *wr,
                  struct ibv_recv_wr **bad_wr);
```

### 参考项目结构

```
erdmaverbs/
├── Cargo.toml
├── src/
│   ├── lib.rs                 # 库入口
│   ├── context.rs            # Device Context
│   ├── pd.rs                 # Protection Domain
│   ├── mr.rs                 # Memory Region
│   ├── cq.rs                 # Completion Queue
│   ├── qp.rs                 # Queue Pair
│   ├── wr.rs                 # Work Request
│   ├── wc.rs                 # Work Completion
│   └── ffi/                  # FFI 绑定
│       └── mod.rs
├── build.rs                  # 绑定生成
└── tests/
    └── basic_test.rs
```

## 实践任务

| 序号 | 任务 | 验收标准 |
|------|------|----------|
| 3.1 | 实现 Context | 能打开/关闭设备 |
| 3.2 | 实现 PD | 能分配/释放保护域 |
| 3.3 | 实现 MR | 能注册内存，返回 lkey/rkey |
| 3.4 | 实现 CQ | 能创建/销毁完成队列 |
| 3.5 | 实现 QP | 能创建 QP，实现状态机转换 |
| 3.6 | 实现 WR | 能发送 Send/Recv WR |
| 3.7 | 实现 WC | 能 poll 到正确的完成事件 |

## 阶段三检查点

- [ ] 理解 RDMA 核心概念 (PD/MR/CQ/QP)
- [ ] 能实现完整的 Verbs API
- [ ] QP 状态机转换正确
- [ ] 内存注册返回正确的 lkey/rkey
- [ ] 完成事件能正确通知应用

---

# 附录

## 技术栈总结

| 层级 | 技术/工具 | 用途 |
|------|----------|------|
| I/O | io-uring / tokio-uring | 高性能异步 I/O |
| 网络 | UDP Socket | RoCEv2 报文收发 |
| FFI | bindgen | C 库绑定生成 |
| 协议 | 手写 RoCEv2 | IB over UDP |
| 测试 | Wireshark | 报文分析 |

## 推荐学习路径

```
第 1-2 周: io_uring 基础
    │
    ├── 官方文档阅读
    ├── 编译运行示例代码
    └── 实现 UDP echo server
           │
           └── 阶段一检查点 ✓
           
第 3-5 周: RoCEv2 协议
    │
    ├── 阅读 IB Spec RoCEv2 章节
    ├── 实现 BTH/AETH/RETH 头部
    ├── 构造完整报文
    └── Wireshark 验证
           │
           └── 阶段二检查点 ✓
           
第 6-10 周: ibverbs API
    │
    ├── 阅读 rust-ibverbs 源码
    ├── 实现 PD/MR/CQ
    ├── 实现 QP 状态机
    ├── 实现 WR/WC
    └── 集成测试
           │
           └── 阶段三检查点 ✓
```

## 参考资料汇总

### io_uring
1. https://docs.rs/io-uring/latest/io_uring/
2. https://docs.rs/tokio-uring/latest/tokio_uring/
3. https://github.com/espoal/uring_examples
4. https://unixism.net/2020/04/io-uring-by-example-1-introduction-to-io_uring/

### RoCEv2 协议
1. https://www.scribd.com/document/350043431/Annex17-RoCEv2
2. https://qsysarch.com/posts/the-infiniband-transport-protocol-of-rocev2/
3. https://docs.nvidia.com/networking/display/winofv55053000/rocev2
4. https://github.com/alexforencich/verilog-ethernet

### ibverbs
1. https://github.com/jonhoo/rust-ibverbs
2. https://docs.rs/crate/ibverbs/latest
3. https://www.rdmamojo.com/
4. https://github.com/datenlord/async-rdma

## 环境安装

```bash
# 安装编译依赖
sudo apt install -y \
    build-essential \
    libclang-dev \
    libnuma-dev \
    librdmacm-dev \
    libibverbs-dev \
    liburing-dev

# 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# 验证安装
cargo --version
rustc --version
```

---

# 方案二：Rust 内核模块实现 (待研究)

## 启动条件

- io_uring 方案完成基础功能后
- 或有充足时间 (6+ 个月)
- 或有明确的学术研究目标

## 参考项目

- [rust-for-linux](https://github.com/Rust-for-Linux/linux)
- [soft-roce](https://github.com/SoftRoCE/rxe-rdma-kernel)

## 待研究内容

- Rust 内核编程约束
- 内存安全与内核兼容性
- 调试与错误排查
