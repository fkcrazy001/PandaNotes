# bochs 驱动解答 —— DRM 子系统全景

本文档解答 `bochs_driver.md` 中提出的所有问题.

### 4.1 pcie subsystem vendor id and device id

你的理解正确。`subsystem_vendor` (svid) 和 `subsystem_device` (sdid) 标识的是"谁把芯片集成到板上"。bochs 驱动匹配的 ID 是 QEMU 虚拟显卡：

```c
.vendor      = 0x1234,    // QEMU 虚拟厂商 ID (不是真实存在的 PCI 厂商)
.device      = 0x1111,    // QEMU VGA 设备
.subvendor   = PCI_SUBVENDOR_ID_REDHAT_QUMRANET,
.subdevice   = PCI_SUBDEVICE_ID_QEMU,
```

### 4.2 probe 函数各步骤答疑

#### `pci_resource_len(pdev, 0)` — bar0 是帧缓冲吗？
是的。bar0 是帧缓冲区域：
- **bar0**: 显存 (framebuffer/VRAM)，存放像素数据
- **bar2**: 寄存器区域 (可能是 MMIO 或 I/O port)，用于控制显卡（设置分辨率、开关显示等）

#### `aperture_remove_conflicting_pci_devices()` — 这是什么？

这个函数位于 `drivers/video/aperture.c`，是 Linux 内核的**通用帧缓冲接管机制**（不是 DRM 特有的）。

**问题背景**：系统启动时，BIOS/UEFI 可能已经设置了一个基本显示模式（如 UEFI GOP），并且有通用驱动（如 efifb、vesafb）在占用帧缓冲。现在 bochs 这个"真正的"显卡驱动要接管显卡，就必须先"踢走"这些临时驱动。

`aperture_remove_conflicting_pci_devices(pdev, "bochs-drm")` 做的事：
1. 检查 `pdev` 的 bar0 (帧缓冲) 范围是否和已注册的 aperture 冲突
2. 如果有冲突，把占用这个范围的设备（如 efifb 平台设备）detach/unregister
3. 如果是 VGA 设备，调用 `vga_remove_vgacon()` 关闭 VGA console
4. 把这个范围标记为 bochs 驱动占有

#### `devm_drm_dev_alloc(&pdev->dev, &bochs_driver, ...)` — 分配什么？`&pdev->dev` 是谁？

```c
bochs = devm_drm_dev_alloc(&pdev->dev, &bochs_driver,
                           struct bochs_device, dev);
```

这是一个**设备资源管理宏**（devm = device managed）。它做三件事：

1. 分配 `struct bochs_device` 内存（其中嵌入了 `struct drm_device dev`）
2. 用 `bochs_driver` 初始化 `drm_device`
3. 把 `&pdev->dev` 设为 `drm_device` 的父设备（`dev->dev = &pdev->dev`）

`&pdev->dev` 是 `pci_dev` 内嵌的通用 `struct device`。Linux 设备模型中，`pci_dev` 包含一个 `struct device dev` 成员，代表这个 PCI 设备在设备模型树中的节点。

**关键关系**：
```
pci_dev.dev   ← 是 PCI 设备的通用设备表示
drm_device    ← 是 DRM 子系统中的"GPU 实例"，它继承自 pci_dev.dev
              （注意：bochs_device → drm_device → dev = &pdev->dev）
```

**为什么**驱动模型这样设计？因为 `drm_device` 要挂载在 `/dev/dri/` 下，而 `pci_dev` 要挂载在 `/sys/bus/pci/` 下，它们是同一个物理设备在不同子系统中的不同"面孔"。

#### `pcim_enable_device(pdev)` — enable pcie device

是的。这个函数向 PCI 配置空间写入，启用设备的 I/O 和 Memory 访问。没有这一步就无法访问 bar0 和 bar2。

#### `pci_set_drvdata(pdev, dev)` — 设置私有数据

是的。将 `drm_device` 指针存到 `pci_dev` 的 driver_data 中。后续 `pci_get_drvdata(pdev)` 就能取回。这是 Linux 驱动的标准模式：在 probe 时存、在 remove/suspend 时取。

#### `drm_dev_register(dev, 0)` — 注册后就能看到 /dev/dri/cardX 了？

是的。`drm_dev_register()` (`drivers/gpu/drm/drm_drv.c:1059`) 做了：

1. 注册 **render node** (`/dev/dri/renderD128`)——如果 driver_features 包含 `DRIVER_RENDER`
2. 注册 **primary node** (`/dev/dri/card0`)——这是主入口，允许模式设置
3. 如果 features 有 `DRIVER_MODESET`，调用 `drm_modeset_register_all()`，把所有的 CRTC、connector、encoder、plane 注册到 sysfs
4. 创建 debugfs 节点

#### `drm_client_setup(dev, NULL)` — 和 fbdev 模拟

你笔记中的 `drm_fbdev_ttm_setup` 在你的内核版本中已经变成了新 API：

```c
// 老 API (旧内核)
drm_fbdev_ttm_setup(dev, 32);

// 新 API (当前内核)
drm_client_setup(dev, NULL);   // 内部调用 drm_fbdev_client_setup()
```

`drm_client_setup()` 创建一个内核内部的 **DRM 客户端**，负责提供 `/dev/fb0`（帧缓冲设备）。它：
1. 分配一个 GEM SHMEM buffer 作为帧缓冲
2. 创建一个 `drm_framebuffer` 包裹它
3. 注册为 `fb_info`，让内核 VT console 和 `cat /dev/fb0` 等操作能使用

这意味着即使没有运行 X11/Wayland，你也能在内核 panic 时看到文本显示。

### 4.3 bochs_hw_init 答疑

#### `ioremap(addr, size)` — 为什么还要 map 一次？

`addr` 是 bar0 的**物理地址**（总线地址）。CPU 不能直接访问物理地址（在启用 MMU 的系统上），必须通过 `ioremap()` 映射到内核虚拟地址空间。

```c
addr = pci_resource_start(pdev, 0);  // 物理地址，如 0xFD000000
size = pci_resource_len(pdev, 0);    // 大小

bochs->fb_map = devm_ioremap_wc(&pdev->dev, addr, size);
// fb_map 现在是内核虚拟地址，可以直接用 readl/writel 或 memcpy 访问
// "wc" 表示 Write-Combine 映射，写显存时性能更好
```

所以 bochs 的 `fb_map` 指向的是 bar0 的虚拟地址映射，写 `fb_map` 等同于写显存。

#### `drmm_vram_helper_init`

在你的内核版本中，这个函数已被移除。bochs 改用 `drm_gem_shmem` 作为内存管理器（见驱动中的 `DRM_GEM_SHMEM_DRIVER_OPS`）。

在旧版本中 `drmm_vram_helper_init` 将 bar0 (VRAM) 注册到 DRM 内存管理中。新版本直接在 `bochs.h` 结构体中存 `fb_map` 和 `fb_size`，在用的时候从 `fb_map` 读取或写入。

#### EDID — 什么是 EDID？

EDID (Extended Display Identification Data) 是显示器的"身份证"，存储在显示器中，通过 I2C 总线读取。它包含：

- 制造商名称、型号、序列号
- 支持的分辨率和刷新率（显示模式列表）
- 物理尺寸 (mm)
- 色彩空间支持

bochs 的 "显示器" 是虚拟的，EDID 数据不一定存在。`bochs_hw_read_edid()` 先读头部 8 字节验证是不是合法的 EDID，如果不是就返回 NULL——此时驱动使用 `drm_add_modes_noedid()` 添加默认模式（用 `defx=1024, defy=768` 作为首选）。

#### Encoder — 什么是 Encoder？

在 DRM 模型中，显示管线的概念顺序是：

```
CRTC (扫描引擎) → Encoder (信号编码器) → Connector (物理接口) → 显示器
```

**Encoder** 将 CRTC 产生的像素数据流转换为具体物理信号的格式：

| Encoder 类型 | 说明 |
|-------------|------|
| `DRM_MODE_ENCODER_TMDS` | HDMI/DVI 的 TMDS 差分信号 |
| `DRM_MODE_ENCODER_LVDS` | 笔记本面板的 LVDS 信号 |
| `DRM_MODE_ENCODER_DP` | DisplayPort |
| `DRM_MODE_ENCODER_VIRTUAL` | 虚拟编码器——正是 bochs 用的类型 |

bochs 是虚拟显卡，不存在真实的物理信号编码过程，所以用 `DRM_MODE_ENCODER_VIRTUAL`——基本是个占位符，只是为了满足 DRM 的 KMS 对象模型要求。

### 4.4 回调函数解答

#### bochs_mode_funcs — 设置什么 mode？为什么大部分是 drm 函数？

`mode_config.funcs` 是**全局显示配置**的回调。bochs 只自定义了两个：

```c
static const struct drm_mode_config_funcs bochs_mode_config_funcs = {
    .fb_create      = drm_gem_fb_create_with_dirty,  // 创建 framebuffer
    .mode_valid     = bochs_mode_config_mode_valid,   // ★ bochs 自定义：检查分辨率是否合法
    .atomic_check   = drm_atomic_helper_check,        // 通用
    .atomic_commit  = drm_atomic_helper_commit,       // 通用
};
```

`mode_valid` 是 bochs 唯一需要自定义的：检查用户要求的 `width*height*pitch` 是否超出 `fb_size`（显存总大小）。

其他函数用 DRM 通用实现是因为 DRM 核心已经提供了标准的检查/提交逻辑，只有硬件特定部分才需要驱动实现。

#### Connector — 什么是 Connector？

**Connector** 代表物理显示接口（VGA 口、HDMI 口、DP 口等）。它：

- 检测是否有显示器插入 (`connection` 状态: connected/disconnected)
- 读取 EDID，获得显示器支持的模式列表
- 提供属性（如 "Broadcast RGB" 色彩范围选择）

bochs 的 connector 类型是 `DRM_MODE_CONNECTOR_VIRTUAL`——虚拟接口，不需要真实的物理检测。

bochs 的 `bochs_connector_helper_funcs` 只有一个函数 `get_modes`：读取 EDID，如果不能读就回退到内核内置的常用分辨率列表（defx/defy）。

大部分 connector_funcs 是 DRM 通用函数，原因同上：DRM 核心已经实现了标准的 fill_modes、destroy、atomic 状态管理。

#### Pipe — 什么是 Pipe？

**Pipe** 是 `drm_simple_display_pipe`，它把**简单硬件**所需的四个 KMS 对象打包在一起：

```c
struct drm_simple_display_pipe {
    struct drm_crtc crtc;           // 扫描引擎
    struct drm_plane plane;         // 主平面
    struct drm_encoder encoder;     // 编码器
    struct drm_connector *connector; // 指向连接器
    const struct drm_simple_display_pipe_funcs *funcs;
};
```

对于只有单输出的简单显卡（USB 显卡、虚拟显卡），这四个对象是固定搭配。pipe 概念让它不需要分别初始化四个对象，`drm_simple_display_pipe_init()` 一步完成。

注意：你的 bochs 内核版本**已经不用 pipe** 了（pipe 在新代码中被标记为 deprecated）。bochs 改用标准做法：在 `bochs_kms_init()` 中逐个调用 `drm_universal_plane_init()` → `drm_crtc_init_with_planes()` → `drm_encoder_init()` → `drm_connector_init()`。

#### Plane — 什么是 Plane？

**Plane** 代表"图层"。现代 GPU 支持多个平面叠加：

```
┌──────────────────────┐
│    Cursor Plane      │  ← 硬件光标 (上层)
├──────────────────────┤
│    Overlay Plane     │  ← 视频叠加层 (可缩放、颜色空间转换)
├──────────────────────┤
│    Primary Plane     │  ← 主画面 (桌面背景、窗口内容)
└──────────────────────┘
         ↓
       CRTC → Encoder → Connector → 屏幕
```

bochs 只有一个 **Primary Plane**（主平面），它是唯一和 CRTC 绑定的平面，负责扫描最基本的帧缓冲输出。bochs 不支持 overlay 和硬件 cursor。

`drm_plane_state` 描述一个平面在某次提交中的状态：绑定了哪个 framebuffer、显示位置 (crtc_x, crtc_y)、裁剪区域、旋转、缩放等。

#### `drm_display_mode` — 描述什么？

```c
struct drm_display_mode {
    int clock;          // 像素时钟 (kHz)
    int hdisplay;       // 水平可见像素数 (如 1920)
    int hsync_start;    // 水平同步开始
    int hsync_end;      // 水平同步结束
    int htotal;         // 水平总像素数 (包含消隐)
    int vdisplay;       // 垂直可见行数 (如 1080)
    int vsync_start;    // 垂直同步开始
    int vsync_end;      // 垂直同步结束
    int vtotal;         // 垂直总行数 (包含消隐)
    int vrefresh;       // 刷新率 (Hz)
    int flags;          // +hsync/-hsync/+vsync/-vsync, interlaced
    char name[32];      // "1920x1080"
};
```

这是 CRTC 向显示器输出的**时序参数**。`bochs_hw_setmode()` 从 mode 中提取 `hdisplay` → `xres`、`vdisplay` → `yres`，然后写入 bochs VBE_DISPI 寄存器。

#### Blank / Unblank — 是什么？

**Blank** = 关闭显示输出（黑屏）。**Unblank** = 恢复显示。bochs 的实现：

```c
static void bochs_hw_blank(struct bochs_device *bochs, bool blank)
{
    // 写 VGA 属性控制器寄存器
    bochs_vga_writeb(bochs, VGA_ATT_W, blank ? 0 : 0x20);
    // blank=true  → 写 0x00 → 屏幕全黑
    // blank=false → 写 0x20 → 启用彩色显示
}
```

blank 在 DPMS (显示器电源管理) 中很重要：系统休眠时先 blank 再关显示器，防止输出乱码。

#### bochs_pipe_funcs 中的 prepare_fb / cleanup_fb — 为什么是 drm 函数？

在你的内核版本中，这些是 drm 通用函数（`drm_gem_plane_helper_prepare_fb` 等），因为 drm 核心已经给出了标准实现：prepare_fb 用于 pin/映射 GEM buffer，cleanup_fb 用于 unpin。简单硬件不需要自定义。

#### bochs_fops — ioctl 函数们

`DEFINE_DRM_GEM_FOPS(bochs_fops)` 展开为：

```c
static const struct file_operations bochs_fops = {
    .owner          = THIS_MODULE,
    .open           = drm_open,          // 统一入口
    .release        = drm_release,
    .unlocked_ioctl = drm_ioctl,         // ★ 核心：分发所有 ioctl
    .mmap           = drm_gem_mmap,      // GEM buffer mmap
    .poll           = drm_poll,          // 等待 vblank 事件
    .read           = drm_read,          // 读取事件
    ...
};
```

所有 DRM 驱动共用 **同一个** `drm_ioctl` 函数。`drm_ioctl` 内部根据 ioctl 命令号查表分发：

```
ioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &res)
         │
         ▼
    drm_ioctl() → 查表 drm_ioctls[] → drm_mode_getresources()
                                       (DRM 核心函数)

ioctl(fd, DRM_IOCTL_MODE_SETCRTC, &crtc)
         │
         ▼
    drm_ioctl() → 查表 → drm_mode_setcrtc() (DRM 核心函数)
                         └→ 调用 bochs_crtc_helper_funcs.mode_set_nofb()
                             └→ bochs_hw_setmode()  (驱动函数)
```

驱动不需要关心 ioctl 的解析和验证，只需要在回调中实现硬件操作。

---

## 五、GEM SHMEM vs TTM

你看到的 bochs 用的是 **GEM SHMEM**，而不是 TTM：

| 特性 | GEM SHMEM | TTM |
|------|-----------|-----|
| **显存来源** | 只用系统内存 (匿名页) | 支持多种：System / GART / VRAM / 私有 |
| **显存迁移** | 不需要（都在 RAM） | `ttm_bo_validate()` 在 VRAM↔System 间迁移 |
| **LRU 驱逐** | 仅支持 pin/madvise | 完整的 LRU + 优先级驱逐 |
| **Swap** | 不支持 | 支持换出到磁盘 |
| **复杂度** | 低 | 高 |
| **适用场景** | 简单显卡、虚拟显卡、USB 显卡 | 独立显卡 (AMDGPU, Nouveau, VMWGFX) |

bochs 是 QEMU 的虚拟显卡，显存就是系统内存，不需要管理 VRAM 和 GART，所以 GEM SHMEM 是最合适的选择。

### Damage Tracking (补充)

bochs 中用到 `drm_atomic_for_each_plane_damage()` ——这是 **伤害追踪** (damage tracking)，用于虚拟化场景的性能优化：

- 用户态只更新 framebuffer 的部分区域时，通过 `DRM_IOCTL_MODE_DIRTYFB` 报告哪些矩形区域变了
- 驱动遍历这些矩形，只把变化的部分传到底层（host），而不是每次传整个 framebuffer
- 对 QEMU/VirtIO-GPU/远程桌面等带宽有限的场景至关重要

---

## 六、bochs 驱动总流程示意

```
模块加载
  │
  └→ drm_module_pci_driver_if_modeset() 注册 PCI 驱动
       │
       内核发现匹配的 PCI 设备
       │
       └→ bochs_pci_probe(pdev)
            │
            ├─ aperture_remove_conflicting_pci_devices()
            │   踢掉 efifb/vesafb 等临时驱动，接管帧缓冲
            │
            ├─ devm_drm_dev_alloc()
            │   分配 bochs_device (内含 drm_device)
            │
            ├─ pcim_enable_device(pdev)
            │   启用 PCI 设备，激活 BAR 空间
            │
            ├─ pci_set_drvdata(pdev, dev)
            │   存储关联，方便后续取回
            │
            ├─ bochs_load()
            │    │
            │    ├─ bochs_hw_init()
            │    │     bar2 → mmio (寄存器), bar0 → fb_map (显存映射)
            │    │     读写 VBE_DISPI 寄存器验证硬件
            │    │
            │    └─ bochs_kms_init()
            │         注: 逐个注册 plane → crtc → encoder → connector
            │         设置回调: mode_config_funcs, plane_funcs,
            │                    crtc_funcs, connector_funcs, ...
            │
            ├─ drm_dev_register(dev, 0)
            │   创建 /dev/dri/cardX (主节点)
            │   创建 /dev/dri/renderDXXX (渲染节点)
            │   注册 sysfs + debugfs
            │
            └─ drm_client_setup(dev, NULL)
                创建 /dev/fb0 (framebuffer console)
```

---

## 七、关键内核文件索引

| 领域 | 文件 | 关键内容 |
|------|------|---------|
| 用户态 API | `include/uapi/drm/drm.h` | ioctl 编号、drm_version、drm_get_cap、事件结构 |
| 用户态 KMS API | `include/uapi/drm/drm_mode.h` | GetResources, GetConnector, SetCrtc, PageFlip, Atomic, CreateDumb |
| ioctl 分发 | `drivers/gpu/drm/drm_ioctl.c` | drm_ioctl() 实现、全量 ioctl 分发表 drm_ioctls[] |
| 设备管理 | `drivers/gpu/drm/drm_drv.c` | drm_dev_register(), drm_dev_unregister() |
| 设备结构 | `include/drm/drm_device.h` | drm_device 定义 |
| 驱动接口 | `include/drm/drm_drv.h` | drm_driver 定义、设备分配宏 |
| CRTC | `include/drm/drm_crtc.h` | CRTC 结构与回调 |
| Connector | `include/drm/drm_connector.h` | Connector 结构与回调 |
| Encoder | `include/drm/drm_encoder.h` | Encoder 结构与回调 |
| Plane | `include/drm/drm_plane.h` | Plane 结构与回调 |
| 显示模式 | `include/drm/drm_mode_config.h` | mode_config 与描述结构 |
| 帧缓冲 | `include/drm/drm_framebuffer.h` | drm_framebuffer 定义 |
| EDID | `include/drm/drm_edid.h` | EDID 解析、drm_edid 结构 |
| GEM | `include/drm/drm_gem.h` | drm_gem_object 基类、DEFINE_DRM_GEM_FOPS |
| GEM SHMEM | `include/drm/drm_gem_shmem_helper.h` | shmem GEM 实现、DRM_GEM_SHMEM_DRIVER_OPS |
| TTM | `include/drm/ttm/ttm_bo_api.h` | TTM buffer object API |
| fbdev 模拟 | `include/drm/drm_fbdev_shmem.h` | fbdev 模拟的 shmem 实现 |
| Atomic | `include/drm/drm_atomic.h` | 原子提交状态机 |
| Damage | `include/drm/drm_damage_helper.h` | 伤害追踪迭代器 |
| vblank | `include/drm/drm_vblank.h` | 垂直消隐管理 |
| Aperture | `drivers/video/aperture.c` | 帧缓冲接管机制 |
| Simple Pipe | `include/drm/drm_simple_kms_helper.h` | 简单 KMS pipe 辅助 |

---

## 八、进一步学习的建议

1. **对比阅读** `drivers/gpu/drm/tiny/` 下其他简单驱动（`cirrus.c`、`gm12u320.c`）——它们和 bochs 结构相似，阅读可加深理解
2. **阅读一个真实 GPU 驱动**的 KMS 部分（如 `drivers/gpu/drm/amd/` 中的 `amdgpu_display.c`）——理解多 CRTC、多 plane、硬件 cursor 的实现方式
3. **写一个简单的 DRM 用户态程序**——直接调用 libdrm API 完成模式设置和 page flip，比读文档更直观
4. **理解 PRIME / DMA-BUF**——这是 GPU 间零拷贝 buffer 共享的基础，也是现代图形栈的核心
