# ebpf gateway

some link:
- [bpf and xdp reference guide](https://docs.cilium.io/en/latest/reference-guides/bpf/index.html)

## 业务场景

基于 `epbf` 技术做一个网关，这个网关主要处理 VPC 之间，以及VPC到经典网络之间的流量。

### 业务逻辑设计

- 三层转发，不需要 MAC 信息
- 基于路由的转发逻辑,VPC 内支持
  - 策略路由(from xxx lookup table xxx), 
  - 自定义路由(ip r add xxx table xxx)，
  - 系统路由(ip route add xxx table main)
- VPC 内的VMNC信息，是 /32 or /128位的精准系统路由
- EIP 支持，1:1的公网ip
- NAT 支持，从 VPC网络 到 经典网络的转发支持
- 可观测性/可调试性

## 开发过程

- 控制面：
  - 自然的接入k8s/restApi, 
  - 提供数据面热加载能力
  - naive 读写 BPF map 能力支持
- 数据面
  - 实现业务逻辑
  - 挂载在 xdp 点： 可能有加速，就算没有加速，内核也有generic xdp可以使用。

结合团队开发情况，使用 Go + c 来开发。

### 数据面开发

- maps design
  - route table: LpmTrieMap
    - key: vpcId + TableId + addr
    - value: route action
  - eip table(and reverse table): hashMap
    - key: vpcId + Ip
    - value: eip
  - ct table: ringbuf?
    - key: tuple(src,dst,srcport,dstport,proto)
    - value: ct action
  - sa pool table: ringbufMap
    - key: none
    - value: addr+port
  - global ip: array
    - key: index
    - value: vip
  
- dp design

xdp =======  is_geneve ===y===> tunnel_process  =====> nat_process: sa_pool fetch && ct create || ct reuse
                ||                   || (in vpc)
                ||                   ===============> Re-encap
                ||                   ||      
                ========> ct_lookup ==>
                            ||
                            =======> to kernel
### 控制面开发

- restApi compat, event driven
  - eBpf maps write/read 
  - announce and revoke bgp

- reload dp on startup (对于我们这种场景，不需要像cilium一样热编译代码)