# virtio-gpu

trys to figure out how virtio-gpu(on top of pcie bus) driver works.

## after pcie probe

although virtio gpu can work on multi-bus. pcie is the most complicated.


virtio_get_shm_region: 获取一块共享内存（在virtio share mem 中定义）,作为vram

中间是一些feature的协商，暂时不懂

virtio_find_vqs: 协商获取 controlle vq 和 cursor vq

virtio_cread_le：  VIRTIO_PCI_CAP_DEVICE_CFG 从 device config 读取配置

virtio_gpu_modeset_init
 - set callback virtio_gpu_mode_funcs
    - virtio_gpu_mode_funcs 的 framebuf 分配是自己写的，最主要的工作似乎设置了一下fb的一些callback。但是callback都是drm的库函数
 - vgdev_output_init
    - virtio_gpu_plane_init: 初始化 primary 和 cursor plane
    - drm_crtc_init_with_planes
 - drm_vblank_init: init vlank 资源，让后续drm能够去处理vblank事件