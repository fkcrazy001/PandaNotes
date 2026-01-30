# kernel

通用准备工作
在开始任何实验之前，请确保你的环境准备就绪：

虚拟机：安装一个 Linux 虚拟机（推荐 Ubuntu 22.04 LTS 或 Fedora），并创建快照，以便随时可以恢复到干净状态。
QEMU & GDB：搭建好 QEMU + GDB 内核调试环境。
内核源码：下载一份你感兴趣的内核源码（如最新的 LTS 版本）。
基础编译：你已经能够独立编译内核并用 QEMU 启动它。
领域一：eBPF 与 高级网络
实验 1：初窥门径 —— 使用 bpftrace 洞察内核
目标：不写一行 C 代码，直观感受 eBPF 的强大威力，学会使用高级工具进行即时追踪。
工具：bpftrace。
步骤：
安装 bpftrace：sudo apt install bpftrace (Ubuntu) 或 sudo dnf install bpftrace (Fedora)。
追踪系统调用：打开一个终端，运行 sudo bpftrace -e 'tracepoint:syscalls:sys_enter_openat { printf("Opening file: %s\n", str(args->filename)); }'。
打开另一个终端，执行一些常见命令，如 ls /tmp，cat /etc/hosts。
观察第一个终端的输出，你会看到所有 openat 系统调用的文件路径都被实时打印出来。
尝试其他 bpftrace 单行命令，例如：sudo bpftrace -e 'kprobe:do_exit { printf("PID %d exited\n", pid); }' 来追踪进程退出。
验证与思考：
验证：是否能看到预期的输出？
思考：bpftrace 是如何做到在不修改、不重编译内核的情况下，获取到这些内部信息的？tracepoint 和 kprobe 有什么区别？
实验 2：登堂入室 —— 使用 BCC/Python 编写 eBPF 应用
目标：学会编写一个包含内核态 eBPF 代码和用户态控制程序的完整应用。
工具：BCC (BPF Compiler Collection), Python。
步骤：
安装 BCC：按照 BCC 安装指南 进行安装。
编写一个 Python 脚本 (hello_bcc.py)。
在脚本中，定义一段 C 语言的 eBPF 程序，该程序使用 kprobe 挂载到 clone 系统调用上，并使用 bpf_trace_printk 打印一条消息。
在 Python 部分，加载并挂载上述 eBPF 程序，然后循环读取 trace_pipe 来显示内核的输出。
运行脚本 sudo python3 hello_bcc.py，并在另一个终端创建新进程（如打开一个新的 shell），观察输出。
验证与思考：
验证：运行脚本后，创建新进程时，是否能看到内核打印的 "Hello, clone!" 之类的消息？
思考：用户态的 Python 脚本和内核态的 C 代码是如何交互的？bpf_trace_printk 是一种简单的调试方式，在生产环境中，我们应该用什么方式（如 BPF Maps, Perf Buffers）将数据从内核传递到用户空间？
实验 3：炉火纯青 —— 使用 libbpf 和 XDP 实现高性能包过滤
目标：理解 XDP (eXpress Data Path) 的原理，并编写一个 C 语言的 XDP 程序来在网卡驱动层丢弃网络包。
工具：libbpf, Clang/LLVM, iproute2, C 语言。
步骤：
安装 libbpf-dev, clang, llvm。
编写一个 C 文件 (xdp_dropper.c)，包含一个 XDP 程序。该程序的功能非常简单：直接返回 XDP_DROP，表示丢弃所有收到的包。
使用 Clang 将其编译成 BPF 字节码（.o 文件）。
找到你的网络接口名称（如 eth0）。
使用 iproute2 命令将你的 XDP 程序加载到网络接口上：sudo ip link set dev eth0 xdp obj xdp_dropper.o sec xdp。
尝试从另一台机器 ping 这个网络接口。
卸载程序：sudo ip link set dev eth0 xdp off。
验证与思考：
验证：加载 XDP 程序后，ping 是否超时？卸载后，ping 是否恢复正常？
思考：为什么 XDP 的性能远高于 iptables？XDP 程序在网络协议栈的哪一层执行？XDP_PASS, XDP_TX, XDP_REDIRECT 各有什么作用？
领域二：异步 I/O: io_uring
实验 1：牛刀小试 —— 使用 fio 对比 I/O 引擎性能
目标：直观感受 io_uring 相比传统异步 I/O (libaio) 的性能优势。
工具：fio (Flexible I/O Tester)。
步骤：
安装 fio：sudo apt install fio。
创建一个大的测试文件：fallocate -l 1G testfile.dat。
使用 libaio 引擎进行随机读测试：fio --name=aio-test --ioengine=libaio --iodepth=64 --rw=randread --bs=4k --size=1G --filename=testfile.dat。记录 IOPS 和延迟。
使用 io_uring 引擎进行同样的测试：fio --name=uring-test --ioengine=io_uring --iodepth=64 --rw=randread --bs=4k --size=1G --filename=testfile.dat。
对比两次测试的 IOPS (每秒 I/O 操作次数) 和延迟 (lat) 结果。
验证与思考：
验证：io_uring 的 IOPS 是否显著高于 libaio？延迟是否更低？
思考：io_uring 为何更快？思考一下系统调用的开销。io_uring 是如何减少系统调用次数的？（提示：SQ 和 CQ 环形缓冲区）。
实验 2：登堂入室 —— 使用 liburing 编写简单的文件拷贝程序
目标：学会使用 liburing 库来提交一个 I/O 请求并处理其完成事件。
工具：liburing, C 语言。
步骤：
安装 liburing-dev。
编写一个 C 程序，实现用 io_uring 将一个文件拷贝到另一个文件。
程序逻辑：初始化 io_uring -> 获取一个提交队列项 (SQE) -> 使用 io_uring_prep_read 准备读操作 -> 提交请求 -> 等待完成队列项 (CQE) -> 从 CQE 获取读操作结果 -> 准备并提交写操作 -> 等待完成 -> 清理退出。
验证与思考：
验证：程序运行后，目标文件内容是否与源文件完全一致？
思考：SQE 和 CQE 是什么？用户空间程序和内核是如何通过它们进行通信的？这个简单的实现是“一次读-等待-一次写”，如何改进才能让读和写并行起来，实现真正的流水线操作？
实验 3：融会贯通 —— 实现 I/O 请求链 (Linked SQEs)
目标：掌握 io_uring 的高级特性，将多个操作链接在一起，由内核按顺序执行，进一步减少用户态/内核态切换。
工具：liburing, C 语言。
步骤：
在实验 2 的基础上修改代码。
一次性准备两个 SQE：一个用于 read，一个用于 write。
在准备第一个（read）SQE 时，设置 IOSQE_IO_LINK 标志。
将这两个 SQE 一次性提交。内核会保证只有在 read 操作成功完成后，才会执行链接的 write 操作。
在循环中处理多个块的拷贝，每次都提交一个 read-write 链。
验证与思考：
验证：文件拷贝是否依然正确？使用 strace 观察，系统调用次数是否比实验 2 的朴素实现更少？
思考：IOSQE_IO_LINK 带来了什么好处？它与自己手动在用户态等待完成再提交下一个请求相比，优势在哪里？io_uring 还可以用于网络、fsync 等非文件 I/O 操作，你能想到哪些应用场景？
领域三：云原生基础：容器与虚拟化
实验 1：手动造轮 —— 使用 unshare 和 chroot 创建简易容器
目标：不使用 Docker，手动模拟容器的创建过程，深刻理解 Namespace 隔离。
工具：unshare, chroot, 一个 rootfs 目录 (如 alpine-minirootfs)。
步骤：
下载一个 Alpine Linux 的迷你根文件系统并解压到 ~/my-container。
运行命令：sudo unshare --fork --pid --mount-proc --mount -- sh -c "chroot ~/my-container /bin/sh"
在新启动的 shell 中，运行 ps aux。你看到了什么？
运行 hostname new-name，然后 hostname。
退出这个 shell，在外部再次运行 hostname。
验证与思考：
验证：在“容器”内，ps 是否只显示了 sh 和 ps 等极少数进程，且 sh 的 PID 是 1？修改的 hostname 是否只在容器内生效？
思考：这个简易容器和 Docker 容器还差了什么？（提示：网络隔离 net ns，用户隔离 user ns，资源限制 Cgroups）。
实验 2：资源铁笼 —— 使用 Cgroups V2 限制进程资源
目标：学会使用 Cgroups V2 接口来限制一个进程的 CPU 和内存使用。
工具：cgcreate, cgexec, 或直接操作 /sys/fs/cgroup 文件系统。
步骤：
创建一个新的 cgroup：sudo mkdir /sys/fs/cgroup/my-slice。
设置 CPU 上限：echo "10000 100000" | sudo tee /sys/fs/cgroup/my-slice/cpu.max (表示每 100ms 最多使用 10ms CPU，即 10%)。
设置内存上限：echo "100M" | sudo tee /sys/fs/cgroup/my-slice/memory.max。
编写一个消耗资源的脚本（如 while true; do :; done 消耗 CPU，或一个分配大量内存的 Python 脚本）。
将该脚本的 PID 写入 cgroup：echo $PID | sudo tee /sys/fs/cgroup/my-slice/cgroup.procs。
使用 top 或 htop 观察该进程的资源使用情况。
验证与思考：
验证：该进程的 CPU 使用率是否被限制在 10% 左右？内存消耗脚本是否在达到 100M 时被 OOM Killer 杀死？
思考：Cgroups V2 相比 V1 有哪些改进？除了 CPU 和内存，Cgroups 还能限制哪些资源？
实验 3：深入 KVM —— 编写最小的虚拟机监视器
目标：理解 KVM 的基本工作模式：通过 /dev/kvm 的 ioctl 来创建和管理虚拟机。
工具：C 语言, gcc。
步骤：
这是一个高难度实验，强烈建议寻找并阅读一个最小的 KVM 示例代码（搜索 "minimal KVM example"）。
编写一个 C 程序，完成以下步骤： a. 打开 /dev/kvm。 b. 使用 KVM_CREATE_VM ioctl 创建一个虚拟机。 c. 为虚拟机分配一小块内存作为 Guest Memory，并使用 KVM_SET_USER_MEMORY_REGION 告知 KVM。 d. 在这块内存的开头写入一个单字节的机器码 0xf4 (HLT 指令)。 e. 使用 KVM_CREATE_VCPU 创建一个虚拟 CPU。 f. 使用 KVM_RUN ioctl 启动 vCPU。
检查 KVM_RUN 的返回值和 kvm_run 结构体中的 exit_reason。
验证与思考：
验证：KVM_RUN 返回后，exit_reason 是否为 KVM_EXIT_HLT？
思考：这个过程是如何工作的？什么是 VM-Exit？当 Guest OS 想要执行 I/O 操作时会发生什么？virtio 在其中扮演了什么角色？
以上计划为你提供了清晰的、逐步深入的实践路径。完成这些实验，你对这些热门领域的理解将远远超越只读书本的层面，真正达到“手中有码，心中有数”的境界。祝你实验顺利，探索愉快！