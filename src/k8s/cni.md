# cni

## 基础功能

CNI 简单来说是给容器配置网络用的, 包括创建网卡，配置路由，配置MTU，删除路由，删除网卡等。

它的调用链如下： kubelet -> crd -> cni， 也就是说动作由 containerd 这样的容器runtime发起。调用的方式是直接通过命令行，传参的方式是环境变量+stdin json.

参考spec: <https://github.com/containernetworking/cni/blob/main/SPEC.md>

代码实现(一个框架，可以方便的开发cni，读取环境变量和stdin 这些都可以让它来做): <https://github.com/containernetworking/cni>


## 扩展功能

可以看到，在基础功能上，cni 是一个无状态的组件。基本上来说就是做一些命令行工具。

但是随着网络的演进（主要是传统的基于iptables的实现会有很多问题，如ct压力大，iptables配置复杂等），现在很多 CNI 把网络方向的活全给干了，比如说NetworkPolicy，QOS，Service等。典型的有 cilium, kube-ovn。

不过 cilium 不能简单的称他为cni，它通常是由 cni + agent(ds) + ebpf 三块组成的，其中 ebpf 实现 L2-L7 层的所有业务逻辑，而agent负责接收 cni 发过来的网卡创建信息，并且还会提供 ipadm 功能。

以 cilium 为例，看看扩展功能的实现。

### network policy （ACL/SG）

- 云原生路径： agent list-watch k8s api server, 监听 networkpolicy
- 云管路径: 部署的 operator 推送数据（创建cr）给 agent

无论怎么样，最终都是通过agent 下发 entry 到 ebpf map中，而数据面匹配逻辑不变

### service

和上面流程类似。