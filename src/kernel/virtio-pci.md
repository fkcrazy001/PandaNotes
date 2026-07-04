# virtio-pci

这一章节讲一下 virtio 设备在pcie总线上的发现流程。

## vid 和 did

- vendor_id: 0x1af4

- device id: 0x1000 - 0x107f: 通常驱动会用 any 来匹配（0xffff）
  - did = 0x1040 + virtio_id[1]
  - Transitional device:  0x1000 to 0x103F

	
| Transitional PCI Device ID |	Virtio Device |
| --- | --- |
| 0x1000 | network card |
| 0x1001 | block device |
| 0x1002 | memory ballooning (traditional)|
| 0x1003 |	console |
| 0x1004 | SCSI host |
| 0x1005 | entropy source |
| 0x1009 |	9P transport |

Transitional devices MUST have a PCI Revision ID of 0.

## device capability

### read/write configuration

要么通过映射 bar 然后通过偏移去访问。对于virtio设备，还可以通过 VIRTIO_PCI_CAP_PCI_CFG capability 在 扩展空间中区访问。

具体说一下方式2,因为确实挺神奇的: 
- 通过capability ptr 字段 找到这个设备的能力区
- 然后找到 vendor_specific 这种能力类型。它具有下面这种结构
```C
struct virtio_pci_cap { 
        u8 cap_vndr;    /* Generic PCI field: PCI_CAP_ID_VNDR */ 
        u8 cap_next;    /* Generic PCI field: next ptr. */ 
        u8 cap_len;     /* Generic PCI field: capability length */ 
        u8 cfg_type;    /* Identifies the structure. */ 
        u8 bar;         /* Where to find it. */ 
        u8 id;          /* Multiple capabilities of the same type */ 
        u8 padding[2];  /* Pad to full dword. */ 
        le32 offset;    /* Offset within bar. */ 
        le32 length;    /* Length of the structure, in bytes. */ 
}; 
struct virtio_pci_cfg_cap { 
        struct virtio_pci_cap cap; 
        u8 pci_cfg_data[4]; /* Data for BAR access. */ 
}; 
```
- 然后往bar，offset，length写入数据，再在 pci_cfg_data 中读出来，就可以获取指定位置上的数据（通过读取 pci_cfg_data）.和用bar访问就是类似的。

cfg type 有以下几种

```C
/* Common configuration */ 
#define VIRTIO_PCI_CAP_COMMON_CFG        1 
/* Notifications */ 
#define VIRTIO_PCI_CAP_NOTIFY_CFG        2 
/* ISR Status */ 
#define VIRTIO_PCI_CAP_ISR_CFG           3 
/* Device specific configuration */ 
#define VIRTIO_PCI_CAP_DEVICE_CFG        4 
/* PCI configuration access */ 
#define VIRTIO_PCI_CAP_PCI_CFG           5 
/* Shared memory region */ 
#define VIRTIO_PCI_CAP_SHARED_MEMORY_CFG 8 
/* Vendor-specific data */ 
#define VIRTIO_PCI_CAP_VENDOR_CFG        9 
```

### common configuration

通过 VIRTIO_PCI_CAP_COMMON_CFG 这种cfg获取bar和偏移之后，要么映射，要么通过 VIRTIO_PCI_CAP_DEVICE_CFG 来读取。

```C
struct virtio_pci_common_cfg { 
        /* About the whole device. */ 
        le32 device_feature_select;     /* read-write */ 
        le32 device_feature;            /* read-only for driver */ 
        le32 driver_feature_select;     /* read-write */ 
        le32 driver_feature;            /* read-write */ 
        le16 config_msix_vector;        /* read-write */ 
        le16 num_queues;                /* read-only for driver */ 
        u8 device_status;               /* read-write */ 
        u8 config_generation;           /* read-only for driver */ 
 
        /* About a specific virtqueue. */ 
        le16 queue_select;              /* read-write */ 
        le16 queue_size;                /* read-write */ 
        le16 queue_msix_vector;         /* read-write */ 
        le16 queue_enable;              /* read-write */ 
        le16 queue_notify_off;          /* read-only for driver */ 
        le64 queue_desc;                /* read-write */ 
        le64 queue_driver;              /* read-write */ 
        le64 queue_device;              /* read-write */ 
        le16 queue_notify_data;         /* read-only for driver */ 
        le16 queue_reset;               /* read-write */ 
}; 
```

### Notification structure layout

VIRTIO_PCI_CAP_NOTIFY_CFG 能力所描述。

```c
struct virtio_pci_notify_cap { 
        struct virtio_pci_cap cap; 
        le32 notify_off_multiplier; /* Multiplier for queue_notify_off. */ 
};

```

是告诉驱动怎么去告知设备，某个qeueu的数据已经ready。

某个 queue 的告知地址如下，在cap.bar中

```c
cap.offset + queue_notify_off * notify_off_multiplier
```

###  ISR status capability

这个是在没有msi-x机制的时候，设备通知驱动的方法。（传统的intx模式）

但是只能通知是队列还是配置发生了中断。所以驱动需要检查所有的队列的used_idx来分辨。

### Shared memory capability

### Device Requirements: Vendor data capability

###  MSI-X Vector Configuration

## ref
1. <https://docs.oasis-open.org/virtio/virtio/v1.2/csd01/virtio-v1.2-csd01.html>