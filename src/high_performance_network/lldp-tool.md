# lldp-tool


LLDP 是一种链路层协议，可以发现链路上的其它设备（需要其他设备同时开启）。

## centos上安装lldp

```shell
yum install lldpd -y
systemctl start lldpd.service
```

## 查看 neighbour 信息
```shell
[root@localhost ~]# lldpcli show neighbors

-------------------------------------------------------------------------------
Interface:    ens2f1np1, via: LLDP, RID: 2, Time: 0 day, 00:25:58
  Chassis:
    ChassisID:    mac 90:74:2e:f0:a0:6e
    SysName:      xxxx
    SysDescr:     H3C Comware Platform Software, Software Version 7.1.070, Release 8307P10
                  H3C S6850-56HF-G
                  Copyright (c) 2004-2024 New H3C Technologies Co., Ltd. All rights reserved.
    MgmtIP:       10.254.55.220
    Capability:   Bridge, on
    Capability:   Router, on
  Port:
    PortID:       ifname HundredGigE1/0/49
    PortDescr:    HundredGigE1/0/49 Interface
    TTL:          121
-------------------------------------------------------------------------------
```