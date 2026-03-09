# RDMA libibverbs 初始化与数据路径指南

*** 这个是AI 生成的参考文档，不一定正确！！！ ***

## 📖 目录
1. [RDMA 初始化流程](#rdma-初始化流程)
2. [数据路径（DP）流程](#数据路径dp流程)
3. [代码示例](#代码示例)
4. [常见问题](#常见问题)

---

## RDMA 初始化流程

### 初始化步骤概览

```
┌─────────────────────────────────────────────────────────────┐
│                    RDMA 初始化流程                           │
└─────────────────────────────────────────────────────────────┘

Step 1: 获取 RDMA 设备
   ↓
Step 2: 打开设备并获取上下文
   ↓
Step 3: 查询设备属性
   ↓
Step 4: 分配保护域（PD）
   ↓
Step 5: 创建完成队列（CQ）
   ↓
Step 6: 创建队列对（QP）
   ↓
Step 7: 注册内存区域（MR）
   ↓
Step 8: 建立连接（可选）
   ↓
✅ 初始化完成，可以开始数据传输
```

---

### 详细初始化步骤

#### **Step 1: 获取 RDMA 设备列表**

```
┌──────────────────────────────────┐
│  ibv_get_device_list()           │
│  获取系统中所有 RDMA 设备         │
└──────────────────────────────────┘
         ↓
    返回设备列表
    ├─ device[0]: mlx5_0
    ├─ device[1]: mlx5_1
    └─ device[2]: NULL (列表结束)
```

**关键信息**：
- 返回 `struct ibv_device **` 指针数组
- 最后一个元素为 NULL
- 需要手动释放：`ibv_free_device_list()`

---

#### **Step 2: 打开设备并获取上下文**

```
┌──────────────────────────────────────────┐
│  ibv_open_device(device)                 │
│  打开选定的 RDMA 设备                     │
└──────────────────────────────────────────┘
         ↓
    返回设备上下文
    ├─ struct ibv_context
    ├─ 包含设备信息
    └─ 用于后续操作
```

**关键信息**：
- 返回 `struct ibv_context *`
- 包含设备的所有信息
- 需要手动释放：`ibv_close_device()`

---

#### **Step 3: 查询设备属性**

```
┌──────────────────────────────────────────┐
│  ibv_query_device(context, &attr)        │
│  获取设备的详细属性                       │
└──────────────────────────────────────────┘
         ↓
    返回设备属性
    ├─ max_qp: 最大队列对数
    ├─ max_cq: 最大完成队列数
    ├─ max_mr: 最大内存区域数
    ├─ max_qp_wr: 队列对最大工作请求
    ├─ max_sge: 最大分散聚集元素
    ├─ max_mr_size: 最大内存注册大小
    └─ hw_ver: 硬件版本
```

**关键信息**：
- 了解硬件能力
- 用于资源规划
- 返回 `struct ibv_device_attr`

---

#### **Step 4: 分配保护域（Protection Domain）**

```
┌──────────────────────────────────────────┐
│  ibv_alloc_pd(context)                   │
│  为设备分配保护域                         │
└──────────────────────────────────────────┘
         ↓
    返回保护域
    ├─ struct ibv_pd
    ├─ 用于内存注册
    ├─ 用于队列对创建
    └─ 用于完成队列创建
```

**关键信息**：
- PD 是内存和队列对的容器
- 同一 PD 内的资源可以相互访问
- 需要手动释放：`ibv_dealloc_pd()`

---

#### **Step 5: 创建完成队列（Completion Queue）**

```
┌──────────────────────────────────────────┐
│  ibv_create_cq(context, cqe, NULL, NULL) │
│  创建完成队列                             │
└──────────────────────────────────────────┘
         ↓
    返回完成队列
    ├─ struct ibv_cq
    ├─ cqe: 完成队列元素数
    ├─ 用于接收完成事件
    └─ 用于轮询完成状态
```

**关键信息**：
- CQ 用于接收操作完成通知
- 可以为 Send CQ 和 Recv CQ 创建不同的队列
- 也可以共用一个 CQ

---

#### **Step 6: 创建队列对（Queue Pair）**

```
┌──────────────────────────────────────────────────────┐
│  ibv_create_qp(pd, &qp_init_attr)                    │
│  创建队列对（RDMA 通信的核心）                        │
└──────────────────────────────────────────────────────┘
         ↓
    返回队列对
    ├─ struct ibv_qp
    ├─ qp_num: 队列对号
    ├─ send_cq: Send 完成队列
    ├─ recv_cq: Recv 完成队列
    ├─ sq_psn: Send 包序列号
    ├─ rq_psn: Recv 包序列号
    └─ qp_state: 初始状态 (RESET)
```

**关键信息**：
- QP 是 RDMA 通信的基本单位
- 需要配置 `struct ibv_qp_init_attr`
- 初始状态为 RESET
- 需要手动释放：`ibv_destroy_qp()`

**QP 初始化属性**：
```c
struct ibv_qp_init_attr {
    void *qp_context;           // 用户定义的上下文
    struct ibv_cq *send_cq;     // Send 完成队列
    struct ibv_cq *recv_cq;     // Recv 完成队列
    struct ibv_srq *srq;        // 共享接收队列（可选）
    struct ibv_qp_cap cap;      // 队列对能力
    enum ibv_qp_type qp_type;   // 队列对类型（IBV_QPT_RC/UC/UD）
    int sq_sig_all;             // 是否所有 Send 都生成完成事件
};
```

---

#### **Step 7: 注册内存区域（Memory Region）**

```
┌──────────────────────────────────────────┐
│  ibv_reg_mr(pd, buf, size, access)       │
│  注册用于 RDMA 的内存区域                 │
└──────────────────────────────────────────┘
         ↓
    返回内存区域
    ├─ struct ibv_mr
    ├─ addr: 内存地址
    ├─ length: 内存大小
    ├─ lkey: 本地密钥（用于 Send/Recv）
    ├─ rkey: 远程密钥（用于 RDMA Write/Read）
    └─ 用于数据传输
```

**关键信息**：
- 必须注册所有用于 RDMA 的内存
- 注册会锁定内存（防止 swap）
- lkey 用于本地操作
- rkey 用于远程操作
- 需要手动释放：`ibv_dereg_mr()`

**访问权限**：
```c
enum ibv_access_flags {
    IBV_ACCESS_LOCAL_WRITE = 1,      // 本地写
    IBV_ACCESS_REMOTE_WRITE = (1 << 1),  // 远程写
    IBV_ACCESS_REMOTE_READ = (1 << 2),   // 远程读
    IBV_ACCESS_REMOTE_ATOMIC = (1 << 3), // 远程原子操作
    IBV_ACCESS_MW_BIND = (1 << 4),       // 内存窗口绑定
};
```

---

#### **Step 8: 建立连接（可选）**

```
┌──────────────────────────────────────────┐
│  修改 QP 状态                             │
│  RESET → INIT → RTR → RTS                │
└──────────────────────────────────────────┘
         ↓
    ┌─────────────────────────────────┐
    │ RESET (初始状态)                 │
    │ ↓ ibv_modify_qp()               │
    │ INIT (初始化)                    │
    │ ↓ ibv_modify_qp()               │
    │ RTR (Ready to Receive)           │
    │ ↓ ibv_modify_qp()               │
    │ RTS (Ready to Send)              │
    │ ✅ 可以发送和接收数据             │
    └─────────────────────────────────┘
```

**QP 状态转换**：
```c
// RESET → INIT
struct ibv_qp_attr attr = {
    .qp_state = IBV_QPS_INIT,
    .pkey_index = 0,
    .port_num = 1,
    .qp_access_flags = IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_REMOTE_READ,
};
ibv_modify_qp(qp, &attr, IBV_QP_STATE | IBV_QP_PKEY_INDEX | 
              IBV_QP_PORT | IBV_QP_ACCESS_FLAGS);

// INIT → RTR
attr.qp_state = IBV_QPS_RTR;
attr.path_mtu = IBV_MTU_1024;
attr.dest_qp_num = remote_qp_num;
attr.rq_psn = remote_psn;
// ... 设置其他属性
ibv_modify_qp(qp, &attr, ...);

// RTR → RTS
attr.qp_state = IBV_QPS_RTS;
attr.sq_psn = local_psn;
attr.timeout = 14;
attr.retry_cnt = 7;
attr.rnr_retry = 7;
ibv_modify_qp(qp, &attr, ...);
```

---

## 数据路径（DP）流程

### 数据路径概览

```
┌─────────────────────────────────────────────────────────────┐
│                    RDMA 数据路径流程                         │
└─────────────────────────────────────────────────────────────┘

应用程序
   ↓
┌──────────────────────────────────────────┐
│ 1. 准备工作请求（Work Request）          │
│    - Send WR / Recv WR                   │
│    - 设置数据缓冲区和长度                 │
└──────────────────────────────────────────┘
   ↓
┌──────────────────────────────────────────┐
│ 2. 提交工作请求到队列对                   │
│    - ibv_post_send() / ibv_post_recv()   │
│    - 请求进入 SQ / RQ                    │
└──────────────────────────────────────────┘
   ↓
┌──────────────────────────────────────────┐
│ 3. 网卡处理请求                           │
│    - 从队列中取出请求                     │
│    - 执行 RDMA 操作                       │
│    - 生成完成事件                         │
└──────────────────────────────────────────┘
   ↓
┌──────────────────────────────────────────┐
│ 4. 轮询或等待完成事件                     │
│    - ibv_poll_cq() / ibv_get_cq_event()  │
│    - 获取完成状态                         │
└──────────────────────────────────────────┘
   ↓
┌──────────────────────────────────────────┐
│ 5. 处理完成事件                           │
│    - 检查操作状态                         │
│    - 处理数据                             │
│    - 继续下一个操作                       │
└──────────────────────────────────────────┘
```

---

### 详细数据路径步骤

#### **Step 1: 准备工作请求（Work Request）**

```
┌─────────────────────────────────────────────────┐
│  struct ibv_send_wr / struct ibv_recv_wr        │
│  定义要执行的 RDMA 操作                          │
└─────────────────────────────────────────────────┘

Send Work Request 结构：
┌──────────────────────────────────────────┐
│ struct ibv_send_wr {                     │
│   uint64_t wr_id;          // 工作请求ID │
│   struct ibv_send_wr *next; // 链表指针  │
│   struct ibv_sge *sg_list;  // 分散聚集  │
│   int num_sge;             // SGE 数量   │
│   enum ibv_wr_opcode opcode; // 操作类型 │
│   int send_flags;          // 发送标志   │
│   union {                                │
│     struct {                             │
│       uint32_t remote_qpn;  // 远程 QPN  │
│       uint32_t remote_qkey; // 远程 QKEY │
│     } ud;                                │
│     struct {                             │
│       uint64_t remote_addr; // 远程地址  │
│       uint32_t rkey;        // 远程密钥  │
│     } rdma;                              │
│   };                                     │
│ };                                       │
└──────────────────────────────────────────┘

Recv Work Request 结构：
┌──────────────────────────────────────────┐
│ struct ibv_recv_wr {                     │
│   uint64_t wr_id;          // 工作请求ID │
│   struct ibv_recv_wr *next; // 链表指针  │
│   struct ibv_sge *sg_list;  // 分散聚集  │
│   int num_sge;             // SGE 数量   │
│ };                                       │
└──────────────────────────────────────────┘

分散聚集元素（SGE）：
┌──────────────────────────────────────────┐
│ struct ibv_sge {                         │
│   uint64_t addr;   // 内存地址            │
│   uint32_t length; // 数据长度            │
│   uint32_t lkey;   // 本地密钥            │
│ };                                       │
└──────────────────────────────────────────┘
```

**操作类型（opcode）**：
```c
enum ibv_wr_opcode {
    IBV_WR_SEND,              // Send 操作
    IBV_WR_SEND_WITH_IMM,     // Send with Immediate
    IBV_WR_RDMA_WRITE,        // RDMA Write
    IBV_WR_RDMA_WRITE_WITH_IMM, // RDMA Write with Immediate
    IBV_WR_RDMA_READ,         // RDMA Read
    IBV_WR_ATOMIC_CMP_AND_SWP, // 原子比较交换
    IBV_WR_ATOMIC_FETCH_AND_ADD, // 原子加
    IBV_WR_LOCAL_INV,         // 本地失效
    IBV_WR_BIND_MW,           // 绑定内存窗口
    IBV_WR_SEND_WITH_INV,     // Send with Invalidate
};
```

---

#### **Step 2: 提交工作请求到队列对**

```
┌─────────────────────────────────────────────────┐
│  ibv_post_send(qp, &wr, &bad_wr)               │
│  或                                             │
│  ibv_post_recv(qp, &wr, &bad_wr)               │
│  提交工作请求到队列对                           │
└─────────────────────────────────────────────────┘

应用程序
   ↓
┌──────────────────────────────────────┐
│ 工作请求链表                          │
│ wr1 → wr2 → wr3 → NULL               │
└──────────────────────────────────────┘
   ↓
┌──────────────────────────────────────┐
│ ibv_post_send() / ibv_post_recv()    │
│ 验证请求                              │
│ 检查队列空间                          │
│ 提交到硬件队列                        │
└──────────────────────────────────────┘
   ↓
┌──────────────────────────────────────┐
│ 队列对（QP）                          │
│ ┌──────────────────────────────────┐ │
│ │ Send Queue (SQ)                  │ │
│ │ [WR1] [WR2] [WR3] [  ] [  ]      │ │
│ └──────────────────────────────────┘ │
│ ┌──────────────────────────────────┐ │
│ │ Recv Queue (RQ)                  │ │
│ │ [WR1] [WR2] [  ] [  ] [  ]       │ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

**关键信息**：
- 可以一次提交多个 WR（链表形式）
- 如果失败，`bad_wr` 指向第一个失败的 WR
- 返回值：0 表示成功，-1 表示失败

---

#### **Step 3: 网卡处理请求**

```
┌─────────────────────────────────────────────────┐
│  网卡硬件处理                                    │
└─────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ 网卡处理流程                                      │
├──────────────────────────────────────────────────┤
│                                                  │
│ 1. 从 SQ 取出工作请求                            │
│    ↓                                             │
│ 2. 解析请求参数                                  │
│    - 操作类型（Send/RDMA Write/Read）            │
│    - 数据地址和长度                              │
│    - 远程地址和密钥（如果是 RDMA 操作）          │
│    ↓                                             │
│ 3. 执行 RDMA 操作                                │
│    ├─ Send: 发送数据到远程 QP                    │
│    ├─ RDMA Write: 写数据到远程内存               │
│    ├─ RDMA Read: 从远程内存读数据                │
│    └─ Atomic: 执行原子操作                       │
│    ↓                                             │
│ 4. 生成完成事件                                  │
│    - 写入完成队列（CQ）                          │
│    - 触发中断（如果启用）                        │
│    ↓                                             │
│ 5. 更新队列指针                                  │
│    - 从 SQ 中移除已处理的 WR                     │
│    ↓                                             │
│ ✅ 操作完成                                      │
│                                                  │
└──────────────────────────────────────────────────┘
```

**RDMA 操作类型**：

```
Send 操作：
┌─────────────┐         ┌─────────────┐
│  发送端 QP  │ ──────→ │  接收端 QP  │
│  Send WR    │  网络   │  Recv WR    │
└─────────────┘         └─────────────┘
  数据进入 RQ，触发完成事件

RDMA Write 操作（One-Sided）：
┌─────────────┐         ┌─────────────┐
│  发送端 QP  │ ──────→ │  远程内存   │
│  RDMA Write │  网络   │  (无需 QP)  │
└─────────────┘         └─────────────┘
  直接写入远程内存，无需远程 CPU 参与

RDMA Read 操作（One-Sided）：
┌─────────────┐         ┌─────────────┐
│  发送端 QP  │ ←────── │  远程内存   │
│  RDMA Read  │  网络   │  (无需 QP)  │
└─────────────┘         └─────────────┘
  直接从远程内存读取数据，无需远程 CPU 参与
```

---

#### **Step 4: 轮询或等待完成事件**

```
┌─────────────────────────────────────────────────┐
│  ibv_poll_cq(cq, num_entries, wc)              │
│  或                                             │
│  ibv_get_cq_event(channel, &cq, &cq_context)   │
│  获取完成事件                                    │
└─────────────────────────────────────────────────┘

完成队列（CQ）结构：
┌──────────────────────────────────────────┐
│ struct ibv_cq {                          │
│   struct ibv_context *context;           │
│   struct ibv_comp_channel *channel;      │
│   void *cq_context;                      │
│   uint32_t handle;                       │
│   int cqe;                               │
│ };                                       │
└──────────────────────────────────────────┘

完成工作条目（WC）结构：
┌──────────────────────────────────────────┐
│ struct ibv_wc {                          │
│   uint64_t wr_id;      // 工作请求 ID    │
│   enum ibv_wc_status status; // 完成状态 │
│   enum ibv_wc_opcode opcode; // 操作类型 │
│   uint32_t vendor_err;  // 厂商错误码    │
│   uint32_t byte_len;    // 传输字节数    │
│   uint32_t imm_data;    // Immediate 数据│
│   uint32_t qp_num;      // 队列对号      │
│   uint32_t src_qp;      // 源 QP 号      │
│   int wc_flags;         // 完成标志      │
│   uint16_t pkey_index;  // 分区键索引    │
│   uint16_t slid;        // 源 LID        │
│   uint8_t sl;           // 服务级别      │
│   uint8_t dlid_path_bits; // DLID 路径位 │
│ };                                       │
└──────────────────────────────────────────┘

轮询方式（Polling）：
┌──────────────────────────────────────────┐
│ while (1) {                              │
│   int ne = ibv_poll_cq(cq, 10, wc);     │
│   if (ne > 0) {                          │
│     for (int i = 0; i < ne; i++) {      │
│       // 处理完成事件                     │
│       if (wc[i].status != IBV_WC_SUCCESS)│
│         // 错误处理                       │
│     }                                    │
│   }                                      │
│ }                                        │
└──────────────────────────────────────────┘

事件驱动方式（Event-Driven）：
┌──────────────────────────────────────────┐
│ // 请求完成事件通知                       │
│ ibv_req_notify_cq(cq, 0);               │
│                                          │
│ // 等待事件                               │
│ struct ibv_cq *ev_cq;                   │
│ void *ev_ctx;                            │
│ ibv_get_cq_event(channel, &ev_cq,       │
│                  &ev_ctx);               │
│                                          │
│ // 确认事件                               │
│ ibv_ack_cq_events(cq, 1);               │
│                                          │
│ // 轮询获取完成条目                       │
│ int ne = ibv_poll_cq(cq, 10, wc);       │
└──────────────────────────────────────────┘
```

**完成状态（status）**：
```c
enum ibv_wc_status {
    IBV_WC_SUCCESS,              // 成功
    IBV_WC_LOC_LEN_ERR,          // 本地长度错误
    IBV_WC_LOC_QP_OP_ERR,        // 本地 QP 操作错误
    IBV_WC_LOC_EEC_OP_ERR,       // 本地 EEC 操作错误
    IBV_WC_LOC_PROT_ERR,         // 本地保护错误
    IBV_WC_WR_FLUSH_ERR,         // 工作请求刷新错误
    IBV_WC_MW_BIND_ERR,          // 内存窗口绑定错误
    IBV_WC_BAD_RESP_ERR,         // 坏响应错误
    IBV_WC_LOC_ACCESS_ERR,       // 本地访问错误
    IBV_WC_REM_INV_REQ_ERR,      // 远程无效请求错误
    IBV_WC_REM_ACCESS_ERR,       // 远程访问错误
    IBV_WC_REM_OP_ERR,           // 远程操作错误
    IBV_WC_RETRY_EXC_ERR,        // 重试超限错误
    IBV_WC_RNR_RETRY_EXC_ERR,    // RNR 重试超限错误
    IBV_WC_LOC_RDD_VIOL_ERR,     // 本地 RDD 违规错误
    IBV_WC_REM_INVALID_RD_REQ_ERR, // 远程无效 RD 请求错误
    IBV_WC_REM_ABORT_ERR,        // 远程中止错误
    IBV_WC_INV_EECN_ERR,         // 无效 EECN 错误
    IBV_WC_INV_EEC_STATE_ERR,    // 无效 EEC 状态错误
    IBV_WC_FATAL_ERR,            // 致命错误
    IBV_WC_RESP_TIMEOUT_ERR,     // 响应超时错误
    IBV_WC_GENERAL_ERR,          // 通用错误
};
```

---

#### **Step 5: 处理完成事件**

```
┌─────────────────────────────────────────────────┐
│  处理完成工作条目（WC）                          │
└─────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ 完成事件处理流程                                  │
├──────────────────────────────────────────────────┤
│                                                  │
│ 1. 检查完成状态                                  │
│    if (wc.status != IBV_WC_SUCCESS) {           │
│      // 错误处理                                 │
│      fprintf(stderr, "Error: %s\n",             │
│              ibv_wc_status_str(wc.status));    │
│      return -1;                                 │
│    }                                            │
│    ↓                                             │
│ 2. 根据操作类型处理                              │
│    switch (wc.opcode) {                         │
│      case IBV_WC_SEND:                          │
│        // Send 操作完成                          │
│        printf("Send completed\n");              │
│        break;                                   │
│      case IBV_WC_RECV:                          │
│        // Recv 操作完成                          │
│        printf("Received %d bytes\n",            │
│                wc.byte_len);                    │
│        break;                                   │
│      case IBV_WC_RDMA_WRITE:                    │
│        // RDMA Write 完成                        │
│        printf("RDMA Write completed\n");        │
│        break;                                   │
│      case IBV_WC_RDMA_READ:                     │
│        // RDMA Read 完成                         │
│        printf("RDMA Read completed\n");         │
│        break;                                   │
│    }                                            │
│    ↓                                             │
│ 3. 处理数据                                      │
│    // 根据 wr_id 找到对应的数据缓冲区            │
│    struct buffer *buf = find_buffer(wc.wr_id); │
│    process_data(buf, wc.byte_len);             │
│    ↓                                             │
│ 4. 继续下一个操作                                │
│    // 如果需要，提交新的工作请求                 │
│    submit_next_wr(qp);                         │
│    ↓                                             │
│ ✅ 处理完成                                      │
│                                                  │
└──────────────────────────────────────────────────┘
```

---

## 代码示例

### 完整的初始化示例

```c
#include <infiniband/verbs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main() {
    // Step 1: 获取设备列表
    int num_devices;
    struct ibv_device **dev_list = ibv_get_device_list(&num_devices);
    if (!dev_list) {
        fprintf(stderr, "Failed to get device list\n");
        return -1;
    }
    printf("Found %d RDMA devices\n", num_devices);

    // Step 2: 打开第一个设备
    struct ibv_context *context = ibv_open_device(dev_list[0]);
    if (!context) {
        fprintf(stderr, "Failed to open device\n");
        ibv_free_device_list(dev_list);
        return -1;
    }
    printf("Device opened successfully\n");

    // Step 3: 查询设备属性
    struct ibv_device_attr device_attr;
    if (ibv_query_device(context, &device_attr)) {
        fprintf(stderr, "Failed to query device\n");
        ibv_close_device(context);
        ibv_free_device_list(dev_list);
        return -1;
    }
    printf("Max QP: %d, Max CQ: %d, Max MR: %d\n",
           device_attr.max_qp, device_attr.max_cq, device_attr.max_mr);

    // Step 4: 分配保护域
    struct ibv_pd *pd = ibv_alloc_pd(context);
    if (!pd) {
        fprintf(stderr, "Failed to allocate PD\n");
        ibv_close_device(context);
        ibv_free_device_list(dev_list);
        return -1;
    }
    printf("PD allocated successfully\n");

    // Step 5: 创建完成队列
    struct ibv_cq *cq = ibv_create_cq(context, 100, NULL, NULL, 0);
    if (!cq) {
        fprintf(stderr, "Failed to create CQ\n");
        ibv_dealloc_pd(pd);
        ibv_close_device(context);
        ibv_free_device_list(dev_list);
        return -1;
    }
    printf("CQ created successfully\n");

    // Step 6: 创建队列对
    struct ibv_qp_init_attr qp_init_attr = {
        .qp_context = NULL,
        .send_cq = cq,
        .recv_cq = cq,
        .srq = NULL,
        .cap = {
            .max_send_wr = 100,
            .max_recv_wr = 100,
            .max_send_sge = 1,
            .max_recv_sge = 1,
            .max_inline_data = 0,
        },
        .qp_type = IBV_QPT_RC,
        .sq_sig_all = 0,
    };

    struct ibv_qp *qp = ibv_create_qp(pd, &qp_init_attr);
    if (!qp) {
        fprintf(stderr, "Failed to create QP\n");
        ibv_destroy_cq(cq);
        ibv_dealloc_pd(pd);
        ibv_close_device(context);
        ibv_free_device_list(dev_list);
        return -1;
    }
    printf("QP created successfully (QP number: %d)\n", qp->qp_num);

    // Step 7: 注册内存区域
    char *buf = malloc(4096);
    struct ibv_mr *mr = ibv_reg_mr(pd, buf, 4096,
                                   IBV_ACCESS_LOCAL_WRITE |
                                   IBV_ACCESS_REMOTE_WRITE |
                                   IBV_ACCESS_REMOTE_READ);
    if (!mr) {
        fprintf(stderr, "Failed to register MR\n");
        free(buf);
        ibv_destroy_qp(qp);
        ibv_destroy_cq(cq);
        ibv_dealloc_pd(pd);
        ibv_close_device(context);
        ibv_free_device_list(dev_list);
        return -1;
    }
    printf("MR registered successfully (lkey: %d, rkey: %d)\n",
           mr->lkey, mr->rkey);

    // 清理资源
    ibv_dereg_mr(mr);
    free(buf);
    ibv_destroy_qp(qp);
    ibv_destroy_cq(cq);
    ibv_dealloc_pd(pd);
    ibv_close_device(context);
    ibv_free_device_list(dev_list);

    printf("Initialization completed successfully!\n");
    return 0;
}
```

---

### 数据路径示例

```c
// Send 操作
struct ibv_sge sge = {
    .addr = (uintptr_t)buf,
    .length = 256,
    .lkey = mr->lkey,
};

struct ibv_send_wr send_wr = {
    .wr_id = 1,
    .next = NULL,
    .sg_list = &sge,
    .num_sge = 1,
    .opcode = IBV_WR_SEND,
    .send_flags = IBV_SEND_SIGNALED,
};

struct ibv_send_wr *bad_wr;
if (ibv_post_send(qp, &send_wr, &bad_wr)) {
    fprintf(stderr, "Failed to post send\n");
    return -1;
}

// 轮询完成事件
struct ibv_wc wc;
int ne = ibv_poll_cq(cq, 1, &wc);
if (ne > 0) {
    if (wc.status == IBV_WC_SUCCESS) {
        printf("Send completed successfully\n");
    } else {
        printf("Send failed: %s\n", ibv_wc_status_str(wc.status));
    }
}
```

---

## 常见问题

### Q1: PD、CQ、QP 之间的关系是什么？
```
PD (保护域)
├─ 用于内存注册
├─ 用于创建 QP
└─ 同一 PD 内的资源可以相互访问

CQ (完成队列)
├─ 接收 Send 操作的完成事件
├─ 接收 Recv 操作的完成事件
└─ 可以为 Send 和 Recv 使用不同的 CQ

QP (队列对)
├─ 属于某个 PD
├─ 使用某个 CQ（或多个 CQ）
└─ 是 RDMA 通信的基本单位
```

### Q2: lkey 和 rkey 有什么区别？
- **lkey**：本地密钥，用于本地操作（Send/Recv）
- **rkey**：远程密钥，用于远程操作（RDMA Write/Read）

### Q3: 为什么需要注册内存？
- 锁定内存，防止被 swap 到磁盘
- 获取 lkey 和 rkey，用于 RDMA 操作
- 网卡需要知道内存的物理地址

### Q4: QP 状态转换的顺序是什么？
```
RESET → INIT → RTR → RTS
```
- **RESET**：初始状态
- **INIT**：初始化状态
- **RTR**：Ready to Receive，可以接收数据
- **RTS**：Ready to Send，可以发送数据

### Q5: Send 和 RDMA Write 有什么区别？
```
Send：
- 两端都需要 QP
- 接收端需要提前 post recv
- 数据进入接收端的 RQ
- 需要接收端的 CPU 参与

RDMA Write：
- 只需要发送端的 QP
- 接收端不需要参与
- 直接写入远程内存
- 接收端的 CPU 不需要参与
```

---

## 总结

### 初始化流程（8 步）
1. 获取设备列表
2. 打开设备
3. 查询设备属性
4. 分配保护域
5. 创建完成队列
6. 创建队列对
7. 注册内存区域
8. 建立连接（修改 QP 状态）

### 数据路径流程（5 步）
1. 准备工作请求
2. 提交工作请求
3. 网卡处理请求
4. 轮询或等待完成事件
5. 处理完成事件

---

**更多资源**：
- [RDMA Mojo](https://www.rdmamojo.com/)
- [libibverbs 官方文档](https://github.com/linux-rdma/rdma-core)
- [Linux RDMA 子系统](https://github.com/torvalds/linux/tree/master/drivers/infiniband)