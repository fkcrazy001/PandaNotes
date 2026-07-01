# bochs driver

this doc is for bochs gpu driver, which locates under `drivers/gpu/drm/tiny/bochs.c`.

this is a tiny kernel gpu driver, and is simple enough to read. Thus I will read to get some basic concepts of gpu driver


## pcie subsystem vendor id and device id

like vid and did, svid is the to declare who made this chip on top of vid;

like NVIDIA 5090 plus msi => msi 5090, with vid and did are 5090, svid and sdid is msi

## probe function

1. fbsize = pci_resource_len(pdev, 0);

get bar0 length, seems this region is framebuf size?

`pci_resource_len()		Returns the byte length of a PCI region`

2. drm_aperture_remove_conflicting_pci_framebuffers ? don't know


3. drm_dev_alloc: alloc a child drm device for &pdev->dev, but for what? and who is &pdev->dev?

4. pcim_enable_device: enable pcie device, that is to write enable to configuration space

5. pci_set_drvdata()               为一个pci_dev设置私有驱动数据指针, that is set drm device to pci-dev


6. bochs_load: see below

7. drm_dev_register: Register the DRM device @dev with the system, advertise device to user-space and start normal device operation. @dev must be initialized via drm_dev_init() previously.

 so now I can see /dev/dri/cardx ?

8. drm_fbdev_ttm_setup :  Setup fbdev emulation for TTM-based drivers ? what is ttm-based drivers? and what is this for?


### bochs_load

1. bochs_hw_init
    
    #define to_pci_dev(n) container_of(n, struct pci_dev, dev), so convert device to pci device. so this device should be &pdev->dev

    if (pdev->resource[2].flags & IORESOURCE_MEM): check if bar3 is a mmio region, if so, register it

    if not(that is a I/O space), so VBE_DISPI_IOPORT_INDEX is set.(a specical io port)


    bochs_dispi_read(bochs, VBE_DISPI_INDEX_ID) && bochs_dispi_read(bochs, VBE_DISPI_INDEX_VIDEO_MEMORY_64K), read reg, get id and memory. if mmio, that is to read bar3

    ```c
    addr = pci_resource_start(pdev, 0);
	size = pci_resource_len(pdev, 0);
    ```
    read bar0, so bar0 is vram addr, and bar3 contains vram info(about how long)

    pci_request_region(pdev, 0): just to see if anyone is using it


    fb_addr = ioremap(addr, size): map again? for what? maybe addr is physic addr?

    check qemu_ext regs, ignore now

2. drmm_vram_helper_init: now register fb to drm memory to let drm manage it. right?

3. bochs_kms_init: set drm config, and set mode config callback funtions

4. bochs_connector_init: what is encoder?
     drm_connector_init: set bochs_connector_connector_funcs callback
     drm_connector_helper_add: set bochs_connector_connector_helper_funcs callback functions
     bochs_hw_load_edid: read mmio to get edid. what is edid?


5. drm_simple_display_pipe_init: set  bochs_pipe_funcs

## callbacks

i suppose these functions is call by drm, but when these functions are called?

### bochs_mode_funcs

set mode for what? and what mode?

most of them are drm functions, why?

###  bochs_connector_connector_funcs

what is connector?

same, are drm functions. why?

### bochs_connector_connector_helper_funcs

only get mode, sees to get mode for a connector?

### bochs_pipe_funcs

what is a pipe? and why a pipe is needed? otherwise pipe, if there is any other mode?

bochs_pipe_enable:
    - bochs_hw_setmode: a lot of bochs internal parameter, xres, yres... means what? and what is a drm display mode, discribed what?
    - bochs_plane_update: what is a plane? what does drm_plane_state  discribes?

bochs_pipe_disable: what is blank and unblank? just blank the entire screen?

bochs_pipe_update: same to bochs_plane_update

prepare_fb & cleanup_fb: functions in drm. why

### ioctl funcs: bochs_fops => common fops from drm

i suppose this is called from userspace(using ioctl)