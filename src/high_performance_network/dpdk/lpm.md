# lpm算法

网上对于 DPDK LPM 算法的描述都有点不清不楚的，还不如官方的描述。

我这里就结合官方的 [文档](./https://doc.dpdk.org/guides/prog_guide/lpm_lib.html#lpm4-details)，然后结合我自己的理解把优劣都说一下。

## 原理

### 基本数据结构

### add rules

### del rules

### lookup rules

## 优势

1. 对于 24bit 以下的掩码，查找复杂度基本可以认为是o(1)的.
2. 用了一个大数组，内存访问会比较友好
3. rcu锁，读完全无锁 (普通的rwlock对cache很不友好，有很多文章都说了rwlock在一些场景下性能甚至不如mutex！)

## 劣势

1. 占用内存大，单个LPM表初始化之后占用就在 60M+
2. KEY 无法扩展，只支持了 IPV4/IPV6，ipv6的字节足够长，可能通过构造也勉强能用
3. nexthop 无法扩展，现在给的是portId， 实际使用的时候往往有更多的需求
4. lpm add/del 最差情况下是o(n)的，主要开销是在 rule 的管理