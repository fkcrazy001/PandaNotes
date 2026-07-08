# vfio

vfio 是一种将vf（virtual function）透传给 qemu/dpdk 这种用户态程序的思路。

总体上来说它想要实现 受控的，用户态访问设备空间的能力。

它在传输层（如pcie）之上，主要描述了访问设备的方法。

## vfio group

入口: (vfio_register_group_dev)

传输层驱动（如vfio-pci）probe到一个设备时，会给这个设备注册一个vfio group，当前可以主要认为是 IOMMU_GROUP下的一个vfio-group. 

> 有些机器没有iommu能力，那也可以通过在加载vfio驱动或者加载完成时，修改 vfio_noiommu 参数为True，不过这个时候kernel会被taint,且kernel要开启 CONFIG_VFIO_NOIOMMU. 之后会为这个设备分配一个 VFIO_NO_IOMMU 的 vfio group。

创建 VFIO GROUP 会创建一个 char dev。 name fmt 是 noiommu-/ "" + group_id (在 vfio_class 下面)

vfio_device_group_register: 对于加入这个vfio group 的设备，最终要记录进来。
vfio_device_debugfs_init: 有一些debugfs，后面再看

## vfio group chr dev ioctl ops

vfio-group 通过 ioctl 对外提供服务，所以研究 fops 是必要的。


```c++
static const struct file_operations vfio_group_fops = {
	.owner		= THIS_MODULE,
	.unlocked_ioctl	= vfio_group_fops_unl_ioctl,
	.compat_ioctl	= compat_ptr_ioctl,
	.open		= vfio_group_fops_open,
	.release	= vfio_group_fops_release,
};
```

### VFIO_GROUP_GET_DEVICE_FD

获取 device 的fd。 通过传入的buf进行match， 而每个match逻辑是 bus 提供的，比如说pcie，就通过bdf匹配，实现逻辑在
`static const struct vfio_device_ops vfio_pci_ops` 中。

### VFIO_GROUP_GET_STATUS

获取一下这个group的状态，比如 VFIO_GROUP_FLAGS_CONTAINER_SET 和 VFIO_GROUP_FLAGS_VIABLE。

### VFIO_GROUP_SET_CONTAINER / VFIO_GROUP_UNSET_CONTAINER

container 管理一组 IOMMU 地址空间，多个GROUP 可以加到同一个container中。 
container 通过 /dev/vfio/vfio 来创建

## vfio_fops 

全局的一些信息，如 api version，给某一个container设置 VFIO_SET_IOMMU

### VFIO_SET_IOMMU

给这个container设置 IOMMU 配置，根据不同的 iommu 驱动类型，来进行注册。注册完了之后，这个container内部的所有iommu就可以被所有的group使用了。

目前 vfio iommu 的驱动有 type1 类型，ppc 和 noiommu 类型。

- type1 就是 vt-d 或者 amd-v 的iommu虚拟化方案，多级页表
- sPAPR TCE 就是ppc 平台上的
- 还有no-iommu, 就是用的物理地址了。

## vfio device open: vfio_device_open_file

在 VFIO_GROUP_GET_DEVICE_FD 时，最终会调用device open，打开这个vfio设备。

后面访问这个设备的空间，就是通过这个fd来的了。所以也要研究一下vfio device 的操作。

这个device是一个匿名文件，所以 fops 在创建时被挂载。 

这些fops只是一个透传，传递到 vfio-device 中去。最终和设备强相关的。（比如说，对于cx6网卡，它需要提供vfio能力，告诉fd应该怎么read/write，怎么mmap）

device fd 的 file_operations 定义在 `vfio_main.c:1456`:

```c
const struct file_operations vfio_device_fops = {
    .open           = vfio_device_fops_cdev_open,
    .release        = vfio_device_fops_release,
    .read           = vfio_device_fops_read,
    .write          = vfio_device_fops_write,
    .unlocked_ioctl = vfio_device_fops_unl_ioctl,
    .mmap           = vfio_device_fops_mmap,
};
```

其中 ioctl 分发逻辑 (`vfio_main.c:1339`)：

```c
static long vfio_device_fops_unl_ioctl(struct file *filep,
                                       unsigned int cmd, unsigned long arg)
{
    struct vfio_device_file *df = filep->private_data;
    struct vfio_device *device = df->device;

    // 特殊 ioctl 直接在 vfio 层处理：
    if (cmd == VFIO_DEVICE_BIND_IOMMUFD)      // 绑定 iommufd
        return vfio_df_ioctl_bind_iommufd(df, uptr);

    if (!smp_load_acquire(&df->access_granted)) // 必须先 open
        return -EINVAL;

    if (IS_ENABLED(CONFIG_VFIO_DEVICE_CDEV) && !df->group) {
        // cdev 路径独有的：attach/detach ioas
        case VFIO_DEVICE_ATTACH_IOMMUFD_PT: ...
        case VFIO_DEVICE_DETACH_IOMMUFD_PT: ...
    }

    // 通用 ioctl：
    case VFIO_DEVICE_FEATURE:           // vfio 层直接处理
    case VFIO_DEVICE_GET_REGION_INFO:   // vfio 层直接处理
    default:                            // 透传给 device->ops->ioctl()
}
```

---

## QEMU/DPDK 的 IOMMU 绑定流程（PCI 为例）

有两种路径：

### 路径 1：传统 container 路径（旧, `/dev/vfio/$GROUP`）

```
QEMU:

1. container_fd = open("/dev/vfio/vfio")
   ioctl(container_fd, VFIO_SET_IOMMU, VFIO_TYPE1_IOMMU)
   → vfio_ioctl_set_iommu → 寻找 vfio_iommu_driver_ops_type1
   → driver->ops->open → 创建 iommu_domain
   → container->iommu_driver = vfio_iommu_driver_ops_type1

2. group_fd = open("/dev/vfio/1")
   ioctl(group_fd, VFIO_GROUP_SET_CONTAINER, &container_fd)
   → vfio_container_attach_group → 把 group 加进 container
   → driver->ops->attach_group → 把 iommu_group 绑到 iommu_domain

3. ioctl(group_fd, VFIO_GROUP_GET_DEVICE_FD, "0000:01:00.0")
   → vfio_device_get_from_name → 调用 pci ops->match (BDF匹配)
   → vfio_device_open_file:
       - vfio_allocate_device_file → 创建 vfio_device_file(df)
       - df->group = device->group   ← group 路径, df 关联 group
       - vfio_df_group_open → vfio_df_open
           → vfio_df_device_first_open:
               vfio_device_group_use_iommu(device) ← 走 container 的 IOMMU
               device->ops->open_device(device)    ← vfio_pci_open_device
                   → vfio_pci_core_enable(pdev)    ← 使能 PCI 设备
                                        (pci_enable_device, bus mastering...)
       - anon_inode_getfile_fmode → 创建匿名文件, fops=vfio_device_fops

4. 后续通过 device_fd 做:
   ioctl(device_fd, VFIO_DEVICE_GET_REGION_INFO) → 获取 BAR 信息
   mmap(device_fd, BAR_space) → 映射 BAR 到用户态
   ioctl(device_fd, VFIO_DEVICE_GET_IRQ_INFO / SET_IRQS) → 中断
```

### 路径 2：iommufd 路径（新, 推荐）

```
QEMU / DPDK:

1. iommufd_fd = open("/dev/iommu")
   ioas = ioctl(iommufd_fd, IOMMU_IOAS_ALLOC) → 分配 IOAS (IO Address Space)

2. device_fd = open("/dev/vfio/devices/vfio0")   ← cdev 路径, 不经过 group
   或者通过 group 路径拿到 device_fd 但走 iommufd 绑定:

3. ioctl(device_fd, VFIO_DEVICE_BIND_IOMMUFD, &bind)
   → vfio_device_fops_unl_ioctl → vfio_df_ioctl_bind_iommufd
   → vfio_df_open → vfio_df_device_first_open
       → vfio_df_iommufd_bind:
           device->ops->bind_iommufd → vfio_iommufd_physical_bind
               → iommufd_device_bind(ictx, vdev->dev, ...)
                   → 把物理设备注册到 iommufd 框架
               vdev->iommufd_device = idev
       → device->ops->open_device → vfio_pci_open_device (使能 PCI)

4. ioctl(device_fd, VFIO_DEVICE_ATTACH_IOMMUFD_PT, &pt)
   → vfio_df_ioctl_attach_pt
   → 如果 ioas_id: device->ops->attach_ioas → vfio_iommufd_physical_attach_ioas
       → iommufd_device_attach(vdev->iommufd_device, pt_id)
           → 把设备绑到指定的 IOAS (IOMMU 页表集合)
   → 如果 hwpt_id: iommufd_device_attach_hwpt
       → 绑到硬件页表 (用于嵌套虚拟化 / vIOMMU)

5. 后续通过 iommufd_fd 做映射:
   ioctl(iommufd_fd, IOMMU_IOAS_MAP) → 在 IOAS 里做 IOVA→HPA 映射
   (所有 attach 到该 IOAS 的设备共享这些映射)
```

---

## 两条路径的核心区别

| | 传统 container 路径 | iommufd 路径 |
|---|---|---|
| IOMMU 管理 fd | `/dev/vfio/vfio` | `/dev/iommu` |
| 绑定方式 | `SET_CONTAINER` → kref 关联 | `BIND_IOMMUFD` → iommufd_device_bind |
| 映射接口 | `VFIO_IOMMU_MAP_DMA` (container_fd) | `IOMMU_IOAS_MAP` (iommufd_fd) |
| Group 语义 | 必须整个 group 交给同一进程 | cdev 直接访问设备, group 约束弱化 |
| IOMMU 域隔离 | container 内所有设备共享 domain | IOAS 粒度控制, 支持多个隔离域 |

---

## open_device 做了什么（PCI 具体）

`vfio_pci_open_device` (`vfio_pci.c:103`):

1. `vfio_pci_core_enable(vdev)` — 调用 `pci_enable_device()`, 设置 bus master, 保存初始 PCI 配置空间作为"干净状态"
2. 如果是 Intel IGD (集成显卡), 额外初始化 OpRegion / GTT stolen memory 等
3. `vfio_pci_core_finish_enable(vdev)` — 让设备进入 `D0` 电源状态

之后用户态才能通过 `VFIO_DEVICE_GET_REGION_INFO` 拿到 BAR 空间信息, 再 `mmap` 这些 BAR。
