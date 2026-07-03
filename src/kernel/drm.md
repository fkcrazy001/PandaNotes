# DRM

---

## 一、DRM 是什么？为什么需要它？

DRM (Direct Rendering Manager) 是 Linux 内核中管理 GPU 的核心子系统。它解决两个根本问题：

1. **多进程共享 GPU**：多个程序同时使用显卡，需要内存管理、权限控制
2. **统一显示模型**：不论 GPU 是什么品牌，用户态通过同一套 API 做模式设置（分辨率切换）和渲染

DRM 在系统中的位置：

```
用户态程序 (X11 / Wayland / 游戏)
        │
        ▼
    libdrm (用户态库，封装 ioctl)
        │
   ═══════════════════════════════ 系统调用边界
        │
        ▼
  /dev/dri/cardX  (DRM 设备文件)
        │
        ▼
   DRM 核心层 (drm_ioctl 分发 → 各子系统)
        │
        ▼
   具体驱动 (bochs / i915 / amdgpu ...)
        │
        ▼
   硬件 (GPU)
```

---

## 二、用户态如何与 DRM 交互？

### 2.1 设备文件

打开 `/dev/dri/card0`（或 `/dev/dri/card1`...），这是一个字符设备。每个 GPU 注册时会创建一个 card 节点作为"主入口"。

```c
int fd = open("/dev/dri/card0", O_RDWR);
```

此外还有 **render node** (`/dev/dri/renderD128`)：仅允许渲染操作（无模式设置权限），供非特权程序使用（如 OpenGL 应用直接渲染到离屏缓冲区）。

### 2.2 libdrm 的作用

libdrm 是用户态封装库。它自己 **不实现任何渲染算法**，核心工作是：

| 功能 | 说明 |
|------|------|
| **封装 ioctl** | 将 `ioctl(fd, DRM_IOCTL_XXX, &arg)` 包装成 `drmModeGetResources(fd)` 这样易用的 C 函数 |
| **资源枚举** | 帮你查询可用 CRTC、connector、encoder，列出支持的显示模式 |
| **内存分配** | 封装 dumb buffer 创建 / mmap，让用户态拿到可写的显存指针 |
| **模式设置** | 封装 SetCrtc / PageFlip / AtomicCommit 等 ioctl |
| **事件机制** | 封装 vblank 事件、page flip 完成事件的读取 |

**libdrm 不是 Mesa/OpenGL 的替代**。Mesa 在 libdrm 之上实现 OpenGL/Vulkan，libdrm 只提供最底层的内核通道。

### 2.3 一张图片从用户态到屏幕的完整流程

以用户态渲染一张图片到显示器为例：

```
1. open("/dev/dri/card0")
   → drm_open() → 分配 drm_file，关联到 drm_device

2. ioctl(DRM_IOCTL_MODE_GETRESOURCES)
   → drm_mode_getresources()
   → 返回：有几个 CRTC、几个 connector、最大分辨率等

3. ioctl(DRM_IOCTL_MODE_GETCONNECTOR, id=connector_0)
   → 读取 EDID（显示器标识数据），返回支持的显示模式列表
   → mode: 1920x1080@60Hz, 1024x768@75Hz, ...

4. ioctl(DRM_IOCTL_MODE_CREATE_DUMB, width=1920, height=1080, bpp=32)
   → bochs: drm_gem_shmem_dumb_create() 在系统内存中分配 1920*1080*4 字节
   → 返回 GEM handle + pitch(每行字节数) + size

5. ioctl(DRM_IOCTL_MODE_MAP_DUMB, handle=xxx)
   → 返回一个 mmap 偏移量

6. mmap(fd, offset) → 得到指向显存(帧缓冲)的虚拟地址指针
   → bochs: 映射的是 bar0 物理地址对应的内核虚拟空间

7. 用户态向这个 mmap 区域写入像素数据 (RGB 值)
   → 直接写入了 bochs 的 VRAM (bar0)

8. ioctl(DRM_IOCTL_MODE_ADDFB, handle=xxx, width, height, pitch, bpp, depth)
   → drm_mode_addfb() → 创建 drm_framebuffer 对象，和 GEM buffer 绑定
   → 返回 fb_id

9. ioctl(DRM_IOCTL_MODE_SETCRTC, crtc_id=0, fb_id=xxx, connector_id=xxx, mode=1920x1080)
   → drm_mode_setcrtc() → 原子提交：
       a. CRTC: 设置为 1920x1080@60Hz 时序
          → bochs: bochs_crtc_helper_mode_set_nofb()
          → bochs_hw_setmode(): 写 VBE_DISPI 寄存器 (XRES/YRES/BPP/ENABLE)
       b. Plane: 将 fb 绑定到 primary plane
          → bochs: bochs_primary_plane_helper_atomic_update()
          → bochs_hw_setbase(): 设置 scanout 起始地址为 0

ioctl(DRM_IOCTL_MODE_DIRTYFB, ...)  ← virtio-gpu 需要这一步

10. 硬件 (QEMU bochs VGA) 开始从 bar0 地址扫描像素输出到显示器
    → 图片显示在屏幕上！

后续如要更新画面 (如播放视频)：
    - 创建另一个 GEM buffer 作为新帧
    - ioctl(DRM_IOCTL_MODE_PAGE_FLIP, fb_id=new_fb)
    - 在下一个 vblank (垂直消隐期) 完成切换，无撕裂
```

---

## 三、DRM 核心层与驱动的关系

### 3.1 DRM 核心为驱动提供了什么？

DRM 核心是"框架层"，向驱动提供通用基础设施：

| 服务 | 说明 |
|------|------|
| **设备生命周期** | `devm_drm_dev_alloc()` 分配设备，`drm_dev_register()` 注册到系统，自动创建 /dev/dri/cardX |
| **IOCTL 分发** | `drm_ioctl()` 统一处理所有 ioctl，根据命令号分发到核心处理函数或驱动的 ioctl 表 |
| **GEM 内存管理** | 提供 `drm_gem_object` 基类 + SHMEM/TTM 实现，driver 只需设置对应 ops |
| **KMS 对象管理** | 提供 connector/encoder/crtc/plane 的结构体定义和注册/注销函数 |
| **Atomic 模式设置** | 提供 `drm_atomic_state` 状态机，驱动只需实现 check/commit 回调 |
| **fbdev 模拟** | 自动创建 `/dev/fb0`，让没有图形环境的阶段（如内核 panic）也能显示文字 |
| **PRIME/DMA-BUF** | 跨设备 buffer 共享，如 GPU 渲染结果直接给显示器 |
| **vblank 与事件** | 垂直同步信号管理和 flip 完成事件队列 |

### 3.2 驱动需要为 DRM 核心提供什么？

以 bochs 驱动为例，驱动需要填充以下关键数据结构：

```c
// 1. 顶层驱动描述
static const struct drm_driver bochs_driver = {
    .driver_features = DRIVER_GEM | DRIVER_MODESET | DRIVER_ATOMIC,
    .fops            = &bochs_fops,           // 文件操作 (open/ioctl/mmap...)
    .name            = "bochs-drm",
    DRM_GEM_SHMEM_DRIVER_OPS,                // GEM 内存 ops
    DRM_FBDEV_SHMEM_DRIVER_OPS,              // fbdev 模拟 ops
};

// 2. KMS 各对象的回调函数
//    驱动在 bochs_kms_init() 中注册以下各组回调：
bochs_primary_plane_funcs       // plane: update/destroy/reset
bochs_primary_plane_helper_funcs // plane: atomic_check/atomic_update
bochs_crtc_funcs                // crtc: reset/set_config/page_flip
bochs_crtc_helper_funcs         // crtc: mode_set/atomic_enable/atomic_disable
bochs_encoder_funcs             // encoder: destroy
bochs_connector_funcs           // connector: fill_modes/destroy/reset
bochs_connector_helper_funcs    // connector: get_modes (读 EDID，上报可用分辨率)
bochs_mode_config_funcs         // mode_config: fb_create/mode_valid/atomic_check/commit

// 3. PCI 驱动注册
static struct pci_driver bochs_pci_driver = {
    .name     = "bochs-drm",
    .id_table = bochs_pci_tbl,
    .probe    = bochs_pci_probe,
};
```

**核心思想**：驱动不处理 ioctl 细节、不管理 /dev/dri/cardX 的创建、不实现 fbdev 模拟的通用逻辑——这些都被 DRM 核心层接管。驱动只需要在回调中告诉 DRM："我的硬件如何设置显示模式"，"我的显存在哪里"。