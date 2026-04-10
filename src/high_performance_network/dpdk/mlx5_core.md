# mlx5驱动

mlx5驱动是给 mellanox CX6 网卡使用的。 

它既有内核态的驱动，也有用户态符合 ibverbs 生态的用户态 *驱动* 。
可能 ibverbs 相关的内容也不能叫驱动。不过确实提供了访问网卡的路径。

此外，对于 DPDK ，它在使用 cx6 网卡时，使用ibverbs库作为访问网卡的途径。
所以在研究完前置条件之后，再把 DPDK 的使用方法再看一看。

## OFED

firmware, driver 等，有一套专门的框架来管理，叫 OFED。

对于内核驱动，可以使用 kernel upstream 的驱动，但是这个更新的可能不如 OFED 那么快。厂商一般也是通过OFED来发行他们的网卡驱动，所以就从OFED入手。

使用的OFED为 MLNX_OFED_LINUX-5.14.0-2.0.1.myos.x86_64.tgz

## linux Kernel Driver: 

## rdma-core


## DPDK
